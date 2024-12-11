#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
#
# sdkmanager.py - part of the F-Droid tools
#
# Copyright (C) 2021, Hans-Christoph Steiner <hans@eds.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import base64
import configparser
import difflib
import gzip
import io
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter, Retry

try:
    from looseversion import LooseVersion
except ImportError:
    # distutils.version was removed in Python 3.12
    import warnings
    from distutils.version import LooseVersion

    warnings.filterwarnings("ignore", category=DeprecationWarning)

COMPATIBLE_VERSION = '26.1.1'

# gitlab.com is disabled because it has Cloudflare blocking enabled and is therefore unreliable
CHECKSUMS_URLS = (
    'https://f-droid.github.io/android-sdk-transparency-log/signed/checksums.json',
    'https://fdroid.gitlab.io/android-sdk-transparency-log/checksums.json',
    # 'https://gitlab.com/fdroid/android-sdk-transparency-log/-/raw/master/signed/checksums.json',
    'https://raw.githubusercontent.com/f-droid/android-sdk-transparency-log/master/signed/checksums.json',
)

HTTP_HEADERS = {'User-Agent': 'F-Droid'}
BUILD_REGEX = re.compile(r'[1-9][0-9]{6}')
NDK_RELEASE_REGEX = re.compile(r'r[1-9][0-9]?[a-z]?(?:-(?:rc|beta)[0-9]+)?')
M2REPOSITORY_REVISION_REGEX = re.compile(r'android_m2repository_r([0-9]+)\.zip')

# The sub-directory to install a given package into, assumes ANDROID_SDK_ROOT as root
# https://developer.android.com/studio/command-line/
INSTALL_DIRS = {
    'build-tools': 'build-tools/{revision}',
    'cmake': 'cmake/{revision}',
    'cmdline-tools': 'cmdline-tools/{revision}',
    'emulator': 'emulator',
    'ndk': 'ndk/{revision}',
    'ndk-bundle': 'ndk-bundle',
    'platforms': 'platforms/{revision}',
    'platform-tools': 'platform-tools',
    'skiaparser': 'skiaparser/{revision}',
    'tools': 'tools',
    'extras;android;m2repository': 'extras/android/m2repository',
}

# NDK releases are like r25b, revisions are like 25.1.8937393. Dir names use revisions.
NDK_REVISIONS = {}

# xsi:type="ns3:genericDetailsType
GENERIC_PACKAGE_XML_TEMPLATE = textwrap.dedent(
    """
    <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <ns2:repository
        xmlns:ns2="http://schemas.android.com/repository/android/common/01"
        xmlns:ns3="http://schemas.android.com/repository/android/generic/01"
        xmlns:ns4="http://schemas.android.com/sdk/android/repo/addon2/01"
        xmlns:ns5="http://schemas.android.com/sdk/android/repo/repository2/01"
        xmlns:ns6="http://schemas.android.com/sdk/android/repo/sys-img2/01">
      <license id="{license_id}" type="text">{license}</license>
      <localPackage path="{path}">
        <type-details xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns3:genericDetailsType"/>
        <revision>{revision}</revision>
        <display-name>PLACEHOLDER</display-name>
        <uses-license ref="{license_id}"/>
      </localPackage>
    </ns2:repository>
"""
).strip()

USAGE = """
Usage:
  sdkmanager [--uninstall] [<common args>] [--package_file=<file>] [<packages>...]
  sdkmanager --update [<common args>]
  sdkmanager --list [<common args>]
  sdkmanager --licenses [<common args>]
  sdkmanager --version

With --install (optional), installs or updates packages.
    By default, the listed packages are installed or (if already installed)
    updated to the latest version.
With --uninstall, uninstall the listed packages.

    <package> is a sdk-style path (e.g. "build-tools;23.0.0" or
             "platforms;android-23").
    <package-file> is a text file where each line is a sdk-style path
                   of a package to install or uninstall.
    Multiple --package_file arguments may be specified in combination
    with explicit paths.

With --update, all installed packages are updated to the latest version.

With --list, all installed and available packages are printed out.

With --licenses, show and offer the option to accept licenses for all
     available packages that have not already been accepted.

With --version, prints the current version of sdkmanager.

Common Arguments:
    --sdk_root=<sdkRootPath>: Use the specified SDK root instead of the SDK
                              containing this tool

    --channel=<channelId>: Include packages in channels up to <channelId>.
                           Common channels are:
                           0 (Stable), 1 (Beta), 2 (Dev), and 3 (Canary).

    --include_obsolete: With --list, show obsolete packages in the
                        package listing. With --update, update obsolete
                        packages as well as non-obsolete.

    --no_https: Force all connections to use http rather than https.

    --proxy=<http | socks>: Connect via a proxy of the given type.

    --proxy_host=<IP or DNS address>: IP or DNS address of the proxy to use.

    --proxy_port=<port #>: Proxy port to connect to.

    --verbose: Enable verbose output.

* If the env var REPO_OS_OVERRIDE is set to "windows",
  "macosx", or "linux", packages will be downloaded for that OS.
"""

ANDROID_SDK_LICENSE = """Terms and Conditions

This is the Android Software Development Kit License Agreement

1. Introduction

1.1 The Android Software Development Kit (referred to in the License Agreement as the "SDK" and specifically including the Android system files, packaged APIs, and Google APIs add-ons) is licensed to you subject to the terms of the License Agreement. The License Agreement forms a legally binding contract between you and Google in relation to your use of the SDK.

1.2 "Android" means the Android software stack for devices, as made available under the Android Open Source Project, which is located at the following URL: http://source.android.com/, as updated from time to time.

1.3 A "compatible implementation" means any Android device that (i) complies with the Android Compatibility Definition document, which can be found at the Android compatibility website (http://source.android.com/compatibility) and which may be updated from time to time; and (ii) successfully passes the Android Compatibility Test Suite (CTS).

1.4 "Google" means Google Inc., a Delaware corporation with principal place of business at 1600 Amphitheatre Parkway, Mountain View, CA 94043, United States.


2. Accepting the License Agreement

2.1 In order to use the SDK, you must first agree to the License Agreement. You may not use the SDK if you do not accept the License Agreement.

2.2 By clicking to accept, you hereby agree to the terms of the License Agreement.

2.3 You may not use the SDK and may not accept the License Agreement if you are a person barred from receiving the SDK under the laws of the United States or other countries, including the country in which you are resident or from which you use the SDK.

2.4 If you are agreeing to be bound by the License Agreement on behalf of your employer or other entity, you represent and warrant that you have full legal authority to bind your employer or such entity to the License Agreement. If you do not have the requisite authority, you may not accept the License Agreement or use the SDK on behalf of your employer or other entity.


3. SDK License from Google

3.1 Subject to the terms of the License Agreement, Google grants you a limited, worldwide, royalty-free, non-assignable, non-exclusive, and non-sublicensable license to use the SDK solely to develop applications for compatible implementations of Android.

3.2 You may not use this SDK to develop applications for other platforms (including non-compatible implementations of Android) or to develop another SDK. You are of course free to develop applications for other platforms, including non-compatible implementations of Android, provided that this SDK is not used for that purpose.

3.3 You agree that Google or third parties own all legal right, title and interest in and to the SDK, including any Intellectual Property Rights that subsist in the SDK. "Intellectual Property Rights" means any and all rights under patent law, copyright law, trade secret law, trademark law, and any and all other proprietary rights. Google reserves all rights not expressly granted to you.

3.4 You may not use the SDK for any purpose not expressly permitted by the License Agreement. Except to the extent required by applicable third party licenses, you may not copy (except for backup purposes), modify, adapt, redistribute, decompile, reverse engineer, disassemble, or create derivative works of the SDK or any part of the SDK.

3.5 Use, reproduction and distribution of components of the SDK licensed under an open source software license are governed solely by the terms of that open source software license and not the License Agreement.

3.6 You agree that the form and nature of the SDK that Google provides may change without prior notice to you and that future versions of the SDK may be incompatible with applications developed on previous versions of the SDK. You agree that Google may stop (permanently or temporarily) providing the SDK (or any features within the SDK) to you or to users generally at Google's sole discretion, without prior notice to you.

3.7 Nothing in the License Agreement gives you a right to use any of Google's trade names, trademarks, service marks, logos, domain names, or other distinctive brand features.

3.8 You agree that you will not remove, obscure, or alter any proprietary rights notices (including copyright and trademark notices) that may be affixed to or contained within the SDK.


4. Use of the SDK by You

4.1 Google agrees that it obtains no right, title or interest from you (or your licensors) under the License Agreement in or to any software applications that you develop using the SDK, including any intellectual property rights that subsist in those applications.

4.2 You agree to use the SDK and write applications only for purposes that are permitted by (a) the License Agreement and (b) any applicable law, regulation or generally accepted practices or guidelines in the relevant jurisdictions (including any laws regarding the export of data or software to and from the United States or other relevant countries).

4.3 You agree that if you use the SDK to develop applications for general public users, you will protect the privacy and legal rights of those users. If the users provide you with user names, passwords, or other login information or personal information, you must make the users aware that the information will be available to your application, and you must provide legally adequate privacy notice and protection for those users. If your application stores personal or sensitive information provided by users, it must do so securely. If the user provides your application with Google Account information, your application may only use that information to access the user's Google Account when, and for the limited purposes for which, the user has given you permission to do so.

4.4 You agree that you will not engage in any activity with the SDK, including the development or distribution of an application, that interferes with, disrupts, damages, or accesses in an unauthorized manner the servers, networks, or other properties or services of any third party including, but not limited to, Google or any mobile communications carrier.

4.5 You agree that you are solely responsible for (and that Google has no responsibility to you or to any third party for) any data, content, or resources that you create, transmit or display through Android and/or applications for Android, and for the consequences of your actions (including any loss or damage which Google may suffer) by doing so.

4.6 You agree that you are solely responsible for (and that Google has no responsibility to you or to any third party for) any breach of your obligations under the License Agreement, any applicable third party contract or Terms of Service, or any applicable law or regulation, and for the consequences (including any loss or damage which Google or any third party may suffer) of any such breach.

5. Your Developer Credentials

5.1 You agree that you are responsible for maintaining the confidentiality of any developer credentials that may be issued to you by Google or which you may choose yourself and that you will be solely responsible for all applications that are developed under your developer credentials.

6. Privacy and Information

6.1 In order to continually innovate and improve the SDK, Google may collect certain usage statistics from the software including but not limited to a unique identifier, associated IP address, version number of the software, and information on which tools and/or services in the SDK are being used and how they are being used. Before any of this information is collected, the SDK will notify you and seek your consent. If you withhold consent, the information will not be collected.

6.2 The data collected is examined in the aggregate to improve the SDK and is maintained in accordance with Google's Privacy Policy.


7. Third Party Applications

7.1 If you use the SDK to run applications developed by a third party or that access data, content or resources provided by a third party, you agree that Google is not responsible for those applications, data, content, or resources. You understand that all data, content or resources which you may access through such third party applications are the sole responsibility of the person from which they originated and that Google is not liable for any loss or damage that you may experience as a result of the use or access of any of those third party applications, data, content, or resources.

7.2 You should be aware the data, content, and resources presented to you through such a third party application may be protected by intellectual property rights which are owned by the providers (or by other persons or companies on their behalf). You may not modify, rent, lease, loan, sell, distribute or create derivative works based on these data, content, or resources (either in whole or in part) unless you have been specifically given permission to do so by the relevant owners.

7.3 You acknowledge that your use of such third party applications, data, content, or resources may be subject to separate terms between you and the relevant third party. In that case, the License Agreement does not affect your legal relationship with these third parties.


8. Using Android APIs

8.1 Google Data APIs

8.1.1 If you use any API to retrieve data from Google, you acknowledge that the data may be protected by intellectual property rights which are owned by Google or those parties that provide the data (or by other persons or companies on their behalf). Your use of any such API may be subject to additional Terms of Service. You may not modify, rent, lease, loan, sell, distribute or create derivative works based on this data (either in whole or in part) unless allowed by the relevant Terms of Service.

8.1.2 If you use any API to retrieve a user's data from Google, you acknowledge and agree that you shall retrieve data only with the user's explicit consent and only when, and for the limited purposes for which, the user has given you permission to do so. If you use the Android Recognition Service API, documented at the following URL: https://developer.android.com/reference/android/speech/RecognitionService, as updated from time to time, you acknowledge that the use of the API is subject to the Data Processing Addendum for Products where Google is a Data Processor, which is located at the following URL: https://privacy.google.com/businesses/gdprprocessorterms/, as updated from time to time. By clicking to accept, you hereby agree to the terms of the Data Processing Addendum for Products where Google is a Data Processor.


9. Terminating the License Agreement

9.1 The License Agreement will continue to apply until terminated by either you or Google as set out below.

9.2 If you want to terminate the License Agreement, you may do so by ceasing your use of the SDK and any relevant developer credentials.

9.3 Google may at any time, terminate the License Agreement with you if: (A) you have breached any provision of the License Agreement; or (B) Google is required to do so by law; or (C) the partner with whom Google offered certain parts of SDK (such as APIs) to you has terminated its relationship with Google or ceased to offer certain parts of the SDK to you; or (D) Google decides to no longer provide the SDK or certain parts of the SDK to users in the country in which you are resident or from which you use the service, or the provision of the SDK or certain SDK services to you by Google is, in Google's sole discretion, no longer commercially viable.

9.4 When the License Agreement comes to an end, all of the legal rights, obligations and liabilities that you and Google have benefited from, been subject to (or which have accrued over time whilst the License Agreement has been in force) or which are expressed to continue indefinitely, shall be unaffected by this cessation, and the provisions of paragraph 14.7 shall continue to apply to such rights, obligations and liabilities indefinitely.


10. DISCLAIMER OF WARRANTIES

10.1 YOU EXPRESSLY UNDERSTAND AND AGREE THAT YOUR USE OF THE SDK IS AT YOUR SOLE RISK AND THAT THE SDK IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTY OF ANY KIND FROM GOOGLE.

10.2 YOUR USE OF THE SDK AND ANY MATERIAL DOWNLOADED OR OTHERWISE OBTAINED THROUGH THE USE OF THE SDK IS AT YOUR OWN DISCRETION AND RISK AND YOU ARE SOLELY RESPONSIBLE FOR ANY DAMAGE TO YOUR COMPUTER SYSTEM OR OTHER DEVICE OR LOSS OF DATA THAT RESULTS FROM SUCH USE.

10.3 GOOGLE FURTHER EXPRESSLY DISCLAIMS ALL WARRANTIES AND CONDITIONS OF ANY KIND, WHETHER EXPRESS OR IMPLIED, INCLUDING, BUT NOT LIMITED TO THE IMPLIED WARRANTIES AND CONDITIONS OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT.


11. LIMITATION OF LIABILITY

11.1 YOU EXPRESSLY UNDERSTAND AND AGREE THAT GOOGLE, ITS SUBSIDIARIES AND AFFILIATES, AND ITS LICENSORS SHALL NOT BE LIABLE TO YOU UNDER ANY THEORY OF LIABILITY FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL OR EXEMPLARY DAMAGES THAT MAY BE INCURRED BY YOU, INCLUDING ANY LOSS OF DATA, WHETHER OR NOT GOOGLE OR ITS REPRESENTATIVES HAVE BEEN ADVISED OF OR SHOULD HAVE BEEN AWARE OF THE POSSIBILITY OF ANY SUCH LOSSES ARISING.


12. Indemnification

12.1 To the maximum extent permitted by law, you agree to defend, indemnify and hold harmless Google, its affiliates and their respective directors, officers, employees and agents from and against any and all claims, actions, suits or proceedings, as well as any and all losses, liabilities, damages, costs and expenses (including reasonable attorneys fees) arising out of or accruing from (a) your use of the SDK, (b) any application you develop on the SDK that infringes any copyright, trademark, trade secret, trade dress, patent or other intellectual property right of any person or defames any person or violates their rights of publicity or privacy, and (c) any non-compliance by you with the License Agreement.


13. Changes to the License Agreement

13.1 Google may make changes to the License Agreement as it distributes new versions of the SDK. When these changes are made, Google will make a new version of the License Agreement available on the website where the SDK is made available.


14. General Legal Terms

14.1 The License Agreement constitutes the whole legal agreement between you and Google and governs your use of the SDK (excluding any services which Google may provide to you under a separate written agreement), and completely replaces any prior agreements between you and Google in relation to the SDK.

14.2 You agree that if Google does not exercise or enforce any legal right or remedy which is contained in the License Agreement (or which Google has the benefit of under any applicable law), this will not be taken to be a formal waiver of Google's rights and that those rights or remedies will still be available to Google.

14.3 If any court of law, having the jurisdiction to decide on this matter, rules that any provision of the License Agreement is invalid, then that provision will be removed from the License Agreement without affecting the rest of the License Agreement. The remaining provisions of the License Agreement will continue to be valid and enforceable.

14.4 You acknowledge and agree that each member of the group of companies of which Google is the parent shall be third party beneficiaries to the License Agreement and that such other companies shall be entitled to directly enforce, and rely upon, any provision of the License Agreement that confers a benefit on (or rights in favor of) them. Other than this, no other person or company shall be third party beneficiaries to the License Agreement.

14.5 EXPORT RESTRICTIONS. THE SDK IS SUBJECT TO UNITED STATES EXPORT LAWS AND REGULATIONS. YOU MUST COMPLY WITH ALL DOMESTIC AND INTERNATIONAL EXPORT LAWS AND REGULATIONS THAT APPLY TO THE SDK. THESE LAWS INCLUDE RESTRICTIONS ON DESTINATIONS, END USERS AND END USE.

14.6 The rights granted in the License Agreement may not be assigned or transferred by either you or Google without the prior written approval of the other party. Neither you nor Google shall be permitted to delegate their responsibilities or obligations under the License Agreement without the prior written approval of the other party.

14.7 The License Agreement, and your relationship with Google under the License Agreement, shall be governed by the laws of the State of California without regard to its conflict of laws provisions. You and Google agree to submit to the exclusive jurisdiction of the courts located within the county of Santa Clara, California to resolve any legal matter arising from the License Agreement. Notwithstanding this, you agree that Google shall still be allowed to apply for injunctive remedies (or an equivalent type of urgent legal relief) in any jurisdiction.


January 16, 2019"""


# This is generated by doing:
#   gpg --export-options export-minimal,export-clean \
#     --export 37D2C98789D8311948394E3E41E7044E1DBA2E89 EE6620C7136B0D2C456C0A4DE9E28DEA00AA5556 \
#   | gzip -9 \
#   | base64 --wrap=88 \
#   > keyring.gpg.gz.base64
KEYRING_GPG_GZ_BASE64 = """
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
36tff69+/b369b+y+vXfAHPyA9GQRwAA
"""

packages = {}
revisions = {}
platform_versions = {}


def requests_retry_session(
    retries=3,
    backoff_factor=0.6,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def get_android_home():
    """Get the pathlib.Path that is the base dir of the Android SDK home

    This first tries the canonical ANDROID_HOME, then tries the
    deprecated ANDROID_SDK_ROOT, then falls back to a sensible,
    hard-coded default.

    https://developer.android.com/studio/command-line/variables#envar

    """
    path = os.getenv('ANDROID_HOME', os.getenv('ANDROID_SDK_ROOT', '/opt/android-sdk'))
    if not path:
        print('ERROR: ANDROID_HOME is set to blank!')
        sys.exit(1)

    android_home = Path(path)
    if not android_home.parent.exists():
        raise FileNotFoundError('ANDROID_HOME "%s" does not exist!' % android_home)
    android_home.mkdir(exist_ok=True)

    return android_home


def get_cachedir():
    cachedir = Path.home() / '.cache/sdkmanager'
    cachedir.mkdir(mode=0o0700, parents=True, exist_ok=True)
    return cachedir


def verify(filename):
    cachedir = get_cachedir()
    keyring = cachedir / 'keyring.gpg'
    with io.BytesIO(base64.b64decode(KEYRING_GPG_GZ_BASE64)) as infp:
        with gzip.GzipFile(fileobj=infp) as gzipfp:
            with keyring.open('wb') as fp:
                fp.write(gzipfp.read())

    if isinstance(filename, str):
        f = filename
    else:
        f = str(filename.resolve())
    p = subprocess.run(
        ['gpgv', '--keyring', str(keyring.resolve()), f + '.asc', f],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if p.returncode == 0:
        return
    print(p.stdout.decode())
    os.remove(f)
    os.remove(f + '.asc')
    raise RuntimeError(f + " failed to verify!")


def download_file(url, local_filename=None):
    """Download a file with some extra tricks for reliability

    The stream=True parameter keeps memory usage low.
    """
    filename = os.path.basename(urlparse(url).path)
    if local_filename is None:
        local_filename = get_cachedir() / filename
    print('Downloading', url, 'into', local_filename)
    r = requests_retry_session().get(
        url, stream=True, allow_redirects=True, headers=HTTP_HEADERS
    )
    r.raise_for_status()
    if r.status_code == 304:
        raise RuntimeError('304 Not Modified: ' + url)
    with local_filename.open('wb') as f:
        for chunk in r.iter_content(chunk_size=io.DEFAULT_BUFFER_SIZE):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    return local_filename


def get_properties_dict(string):
    config = configparser.ConfigParser(delimiters=('='))
    config.read_string('[DEFAULT]\n' + string)
    return dict(config.items('DEFAULT'))


def _add_to_revisions(url, source_properties):
    pkg_revision = source_properties.get('pkg.revision')
    if pkg_revision:
        revisions[url] = tuple(LooseVersion(pkg_revision).version)


def parse_build_tools(url, d):
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        revision = source_properties['pkg.revision'].replace(' ', '-')
        key = ('build-tools', revision)
        if key not in packages:
            packages[key] = url


def parse_cmake(url, d):
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        key = tuple(source_properties['pkg.path'].split(';'))
        if key not in packages:
            packages[key] = url


def parse_cmdline_tools(url, d):
    """Set up cmdline-tools with versioned and 'latest' package name"""
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        key = tuple(source_properties['pkg.path'].split(';'))
        if key not in packages:
            packages[key] = url

    v = re.compile(r'^[0-9.]+$')
    highest = None
    for key, url in packages.items():
        if key[0] != 'cmdline-tools' or len(key) < 2:
            continue
        version = key[-1]
        if version == 'latest':
            continue
        if highest is None:
            highest = version
        elif v.match(version) and LooseVersion(version) > LooseVersion(highest):
            highest = version
    # TODO choose version for 'latest' based on --channel
    # https://developer.android.com/studio/releases/cmdline-tools
    packages[('cmdline-tools', 'latest')] = packages[('cmdline-tools', highest)]


def parse_emulator(url, d):
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        key = tuple(source_properties['pkg.path'].split(';'))
        if key not in packages:
            packages[key] = url
        versioned = (key[0], source_properties['pkg.revision'])
        if versioned in packages:
            packages[versioned] = sorted([url, packages[key]])[-1]
        else:
            packages[versioned] = url


def parse_m2repository(url, d):
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        # source.properties does not reliably contain Pkg.Revision or the path info
        m = M2REPOSITORY_REVISION_REGEX.search(url)
        if m:
            revision = m.group(1)
            key = ('extras', 'android', 'm2repository')
            packages[key] = url
            versioned = key + tuple([revision])
            if versioned not in packages:
                packages[versioned] = url
            noleading0 = key + tuple([revision.lstrip('0')])
            if noleading0 not in packages:
                packages[noleading0] = url


def parse_ndk(url, d):
    revision = None
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        revision = source_properties['pkg.revision']
        for k in ('ndk', 'ndk-bundle'):
            key = (k, revision)
            if key not in packages:
                packages[key] = url
    m = NDK_RELEASE_REGEX.search(url)
    if m:
        release = m.group()
        if revision:
            NDK_REVISIONS[release] = revision
        packages[('ndk', release)] = url
        packages[('ndk-bundle', release)] = url
        # add fake revision for NDKs without source.properties
        if url not in revisions:
            revisions[url] = (1,)
            vstring = re.search(r"android-ndk-r(\d*)([a-z])-linux", url)
            if vstring:
                revisions[url] = (
                    int(vstring.group(1)),
                    ord(vstring.group(2)) - ord("a"),
                )


def parse_platforms(url, d):
    """Parse platforms and choose the URL with the highest release number

    These packages are installed by API version,
    e.g. platforms;android-29, but there are multiple releases
    available, e.g. platform-29_r05.zip, platform-29_r04.zip, etc.

    The build property ro.build.version.codename with the value of REL
    means a full release, rather than preview/beta/etc.  That value
    was not always present, but those releases oly hve a single
    package.

    platform24_r01.zip was released twice, the first being a mistake
    with a platform.version of 'N' in source.properties.

    """
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        apilevel = source_properties['androidversion.apilevel']
        # TODO this should make all versions/revisions available, not only most recent
        key = ('platforms', 'android-%s' % apilevel)
        vstring = '%s.%s' % (
            source_properties.get('platform.version'),
            source_properties.get('pkg.revision'),
        )
        if re.match(r'^[1-9].*', vstring):
            if key not in platform_versions:
                platform_versions[key] = []
            platform_version = LooseVersion(vstring)
            platform_versions[key].append(platform_version)
            if key in packages:
                if platform_version == sorted(platform_versions[key])[-1]:
                    packages[key] = url
            else:
                packages[key] = url


def parse_platform_tools(url, d):
    """Find all platform-tools packages and set highest version as 'platform-tools'"""
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        key = ('platform-tools', source_properties.get('pkg.revision'))
        if key not in packages:
            packages[key] = url

    highest = '0'
    for key, url in packages.items():
        if key[0] != 'platform-tools' or len(key) < 2:
            continue
        version = key[-1]
        if LooseVersion(version) > LooseVersion(highest):
            highest = version
    packages[('platform-tools',)] = packages[('platform-tools', highest)]


def parse_tools(url, d):
    """Find all tools packages and set highest version as 'tools'"""
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        path = source_properties.get('pkg.path')
        if not path:
            path = 'tools'
        key = (path, source_properties.get('pkg.revision'))
        if key not in packages:
            packages[key] = url

    highest = '0'
    for key, url in packages.items():
        if key[0] != 'tools' or len(key) < 2:
            continue
        version = key[-1]
        if LooseVersion(version) > LooseVersion(highest):
            highest = version
    packages[('tools',)] = packages[('tools', highest)]


def parse_skiaparser(url, d):
    """Set up skiaparser with versioned and unversioned package name"""
    if 'source.properties' in d:
        source_properties = get_properties_dict(d['source.properties'])
        _add_to_revisions(url, source_properties)
        key = tuple(source_properties['pkg.path'].split(';'))
        if key in packages:
            packages[key] = sorted([url, packages[key]])[-1]
        else:
            packages[key] = url


def parse_repositories_cfg(f):
    """Parse the supplied repositories.cfg and return a list of URLs"""
    with Path(f).open() as fp:
        data = get_properties_dict(fp.read())

    disabled = set()
    for k, v in data.items():
        if k.startswith('@disabled@'):
            if v == 'disabled':
                url = k.split('@')[2]
                disabled.add(url)

    count = int(data.get('count', '0'))
    i = 0
    repositories = []
    while i < count:
        d = {}
        for k in ('disp', 'dist', 'enabled', 'src'):
            key_i = '%s%02d' % (k, i)
            if data.get(key_i):
                d[k] = data[key_i]
        if d[k] not in disabled:
            repositories.append(d)
        i += 1
    enabled_repositories = []
    for d in repositories:
        v = d.get('enabled', 'true')
        if v == 'true':
            url = d.get('src', '').replace('\\', '')
            if url and url not in enabled_repositories:
                enabled_repositories.append(url)
    return enabled_repositories


# TODO allow : and - as separator, e.g. ndk-22.1.7171670
# only use android-sdk-transparency-log as source
def build_package_list(use_net=False):
    cachedir = get_cachedir()
    cached_checksums = cachedir / 'checksums.json'
    cached_checksums_signature = cachedir / (cached_checksums.name + '.asc')
    if cached_checksums.exists() and cached_checksums_signature.exists():
        verify(cached_checksums)
        with cached_checksums.open() as fp:
            _process_checksums(json.load(fp))
    else:
        use_net = True  # need to fetch checksums.json, no cached version

    etag_file = cached_checksums.parent / (cached_checksums.name + '.etag')
    if etag_file.exists():
        etag = etag_file.read_text()
    else:
        etag = None

    if use_net:
        checksums_url = CHECKSUMS_URLS[random.randint(0, len(CHECKSUMS_URLS) - 1)]
        download_file(checksums_url + '.asc')

        try:
            headers = HTTP_HEADERS.copy()
            if etag:
                headers['If-None-Match'] = etag

            r = requests_retry_session().get(
                checksums_url, allow_redirects=True, headers=headers
            )
        except ValueError as e:
            if etag_file.exists():
                etag_file.unlink()
            print('ERROR:', e)
            sys.exit(1)
        r.raise_for_status()

        if etag is None or etag != r.headers.get('etag'):
            print('Downloading', checksums_url, 'into', str(cached_checksums))
            cached_checksums.write_bytes(r.content)
            verify(cached_checksums)
            etag_file.write_text(r.headers['etag'])
            _process_checksums(r.json())


def _process_checksums(checksums):
    for url in checksums.keys():
        if not url.endswith('.zip'):
            continue

        basename = os.path.basename(url)
        if basename.startswith('build-tools'):
            for entry in checksums[url]:
                parse_build_tools(url, entry)
        elif basename.startswith('cmake'):
            for entry in checksums[url]:
                parse_cmake(url, entry)
        elif basename.startswith('cmdline-tools') or basename.startswith(
            'commandlinetools'
        ):
            for entry in checksums[url]:
                parse_cmdline_tools(url, entry)
        elif basename.startswith('emulator'):
            for entry in checksums[url]:
                parse_emulator(url, entry)
        elif basename.startswith('android_m2repository_r'):
            for entry in checksums[url]:
                parse_m2repository(url, entry)
        elif 'ndk-' in url:
            parse_ndk(url, checksums[url][0])
        elif basename.startswith('platform-tools'):
            for entry in checksums[url]:
                parse_platform_tools(url, entry)
        elif basename.startswith('android-') or basename.startswith('platform-'):
            for entry in checksums[url]:
                parse_platforms(url, entry)
        elif basename.startswith('skiaparser'):
            for entry in checksums[url]:
                parse_skiaparser(url, entry)
        elif basename.startswith('tools') or basename.startswith('sdk-tools-'):
            for entry in checksums[url]:
                parse_tools(url, entry)


def licenses():
    """Prompt the user to accept the various licenses

    TODO actually implement it, this largely fakes it.

    https://cs.android.com/android-studio/platform/tools/base/+/mirror-goog-studio-main:sdklib/src/main/java/com/android/sdklib/tool/sdkmanager/LicensesAction.java
    https://cs.android.com/android-studio/platform/tools/base/+/mirror-goog-studio-main:repository/src/main/java/com/android/repository/api/License.java

    """
    known_licenses = {
        'android-sdk-license': '\n8933bad161af4178b1185d1a37fbf41ea5269c55\n\nd56f5187479451eabf01fb78af6dfcb131a6481e\n24333f8a63b6825ea9c5514f83c2829b004d1fee',
        'android-sdk-preview-license': '\n84831b9409646a918e30573bab4c9c91346d8abd\n',
        'android-sdk-preview-license-old': '79120722343a6f314e0719f863036c702b0e6b2a\n\n84831b9409646a918e30573bab4c9c91346d8abd',
        'intel-android-extra-license': '\nd975f751698a77b662f1254ddbeed3901e976f5a\n',
    }
    known_license_hashes = set()
    for license_value in known_licenses.values():
        for license in license_value.strip().split('\n'):
            if license:
                known_license_hashes.add(license)

    found_license_hashes = set()
    licenses_dir = get_android_home() / 'licenses'
    for f in licenses_dir.glob('*'):
        with f.open() as fp:
            for license in fp.read().strip().split('\n'):
                if license:
                    found_license_hashes.add(license)

    total = len(known_license_hashes)
    license_count = total - len(found_license_hashes)
    if license_count == 0:
        print('All SDK package licenses accepted.')
        return
    if license_count == 1:
        fl = ('1', '1', '', 's')
    else:
        fl = (license_count, total, 's', 've')
    msg = (
        "{0} of {1} SDK package license{2} not accepted.\n"
        "Review license{2} that ha{3} not been accepted (y/N)? "
    ).format(*fl)
    s = input(msg)
    print()
    if s.lower() in ('y', 'yes'):
        licenses_dir.mkdir(exist_ok=True)
        for h in known_license_hashes:
            if h not in found_license_hashes:
                for license_file, known in known_licenses.items():
                    if h in known:
                        with (licenses_dir / license_file).open('w') as fp:
                            fp.write(known)


def install(to_install, android_home=None):
    """Install specified packages, including downloading them as needed

    Certain packages are installed into versioned sub-directories
    while others are always installed into the same location.  These
    installed packages will at least always have 'source.properties'.

    Parameters
    ----------
    to_install
        A single package or list of packages to install.

    android_home
        Optionally provide the ANDROID_HOME path as the install location.

    """
    global packages

    if android_home is None:
        android_home = get_android_home()
    if isinstance(android_home, str):
        android_home = Path(android_home)

    if isinstance(to_install, str):
        to_install = [to_install]
    for package in to_install:
        key = tuple(package.split(';'))
        if key not in packages:
            print("""Warning: Failed to find package '%s'""" % package)
            package_names = [';'.join(n) for n in packages]
            m = difflib.get_close_matches(package, package_names, 1)
            if m:
                print("""Did you mean '%s'?""" % m[0])
            sys.exit(1)
        url = packages[key]

        if key[0] == 'extras' and len(key) in (3, 4):
            name = ';'.join(key[:3])
        else:
            name = key[0]

        if len(key) > 1:
            if key[0] == 'ndk':
                revision = NDK_REVISIONS.get(key[-1], key[-1])
            else:
                revision = key[-1]
            install_dir = android_home / INSTALL_DIRS[name].format(revision=revision)
        else:
            install_dir = android_home / INSTALL_DIRS[name]
        if install_dir.exists():
            continue

        zipball = get_cachedir() / os.path.basename(url)
        if not zipball.exists():
            download_file(url, zipball)

        install_dir.parent.mkdir(parents=True, exist_ok=True)
        _install_zipball_from_cache(zipball, install_dir)
        _generate_package_xml(install_dir, package, url)


def _install_zipball_from_cache(zipball, install_dir):
    unzip_dir = Path(tempfile.mkdtemp(prefix='.sdkmanager-'))

    print('Unzipping to %s' % unzip_dir)
    toplevels = set()
    try:
        with zipfile.ZipFile(str(zipball)) as zipfp:
            for info in zipfp.infolist():
                permbits = info.external_attr >> 16
                writefile = str(unzip_dir / info.filename)
                if stat.S_ISLNK(permbits):
                    link = unzip_dir / info.filename
                    link.parent.mkdir(0o755, parents=True, exist_ok=True)
                    link_target = zipfp.read(info).decode()
                    os.symlink(link_target, str(link))

                    try:
                        link.resolve().relative_to(unzip_dir)
                    except (FileNotFoundError, ValueError):
                        link.unlink()
                        trim_at = len(str(unzip_dir)) + 1
                        print(
                            'ERROR: Unexpected symlink target: {link} -> {target}'.format(
                                link=str(link)[trim_at:], target=link_target
                            )
                        )
                elif stat.S_ISDIR(permbits) or stat.S_IXUSR & permbits:
                    zipfp.extract(info.filename, path=str(unzip_dir))
                    os.chmod(writefile, 0o755)  # nosec bandit B103
                else:
                    zipfp.extract(info.filename, path=str(unzip_dir))
                    os.chmod(writefile, 0o644)  # nosec bandit B103
            toplevels.update([p.split('/')[0] for p in zipfp.namelist()])
    except zipfile.BadZipFile as e:
        print('ERROR:', e)
        if zipball.exists():
            zipball.unlink()
        return

    print('Installing into', install_dir)
    if len(toplevels) == 1:
        extracted = [d for d in unzip_dir.iterdir()][0]
        shutil.move(str(extracted), str(install_dir))
    else:
        install_dir.mkdir(parents=True)
        for extracted in unzip_dir.iterdir():
            shutil.move(str(extracted), str(install_dir))
    if zipball.exists():
        zipball.unlink()


def _generate_package_xml(install_dir, package, url):
    """Generate package.xml for an installed package

    TODO: This does not yet work for all package types.  Gradle Android
    Plugin work better with no package.xml than wrong one.

    """
    package_base = package.split(';')[0]
    if package_base in ('extras', 'platforms', 'sources', 'system-images'):
        return

    # These packages should never have the version in the path.
    if package_base in ('emulator', 'ndk-bundle', 'tools'):
        package = package_base

    revision = revisions[url]

    if package_base == 'ndk':
        package = f"ndk;{'.'.join((str(x) for x in revision))}"

    template = ('<major>{0}</major>', '<minor>{1}</minor>', '<micro>{2}</micro>')
    r = min(3, len(revision))
    d = {
        'license': ANDROID_SDK_LICENSE,
        'license_id': 'android-sdk-license',
        'path': package,
        'revision': ''.join(template[:r]).format(*revision),
    }
    with (install_dir / 'package.xml').open('w') as fp:
        fp.write(GENERIC_PACKAGE_XML_TEMPLATE.format(**d))


def list():
    global packages

    path_width = 0
    names = []
    for package in packages:
        name = ';'.join(package)
        if len(name) > path_width:
            path_width = len(name)
        names.append(name)
    print('Installed Packages:')
    print('  ' + 'Path'.ljust(path_width) + ' | Version       | Description | Location')
    print(
        '  ' + '-------'.ljust(path_width) + ' | -------       | -------     | -------'
    )
    print()
    print('Available Packages:')
    print('  ' + 'Path'.ljust(path_width) + ' | Version       | Description')
    print('  ' + '-------'.ljust(path_width) + ' | -------       | -------')
    for name in sorted(names):
        print('  %s |               | ' % name.ljust(path_width))


def main():
    parser = argparse.ArgumentParser()
    # commands
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--licenses", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--version", action="store_true")

    # "common arguments"
    parser.add_argument("--channel")
    parser.add_argument("--include_obsolete")
    parser.add_argument("--no_https")
    parser.add_argument("--proxy")
    parser.add_argument("--proxy_host")
    parser.add_argument("--proxy_port")
    parser.add_argument("--sdk_root")
    parser.add_argument(
        "--verbose", action="store_true", help="increase output verbosity"
    )

    parser.add_argument('packages', nargs='*')

    # do not require argcomplete to keep the install profile light
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    args = parser.parse_args()
    command = None
    for k in ('install', 'licenses', 'list', 'uninstall', 'update', 'version'):
        if args.__dict__[k]:
            if command is not None:
                print(
                    'Error: Only one of --uninstall, --install, --licenses, '
                    '--update, --list, --version can be specified.'
                )
                print(USAGE)
                sys.exit(1)
            command = k
    if command is None:
        command = 'install'
    elif command == 'version':
        print('25.2.0')
        sys.exit()

    method = globals().get(command)
    if not method:
        raise NotImplementedError('Command "--%s" not implemented' % command)
    if command in ('install', 'uninstall'):
        build_package_list(use_net=False)
        method(args.packages)
    else:
        build_package_list(use_net=True)
        method()


if __name__ == "__main__":
    main()
