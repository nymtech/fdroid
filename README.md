# Install instructions for NymVPN via F-Droid private repo
This repository hosts an [F-Droid](https://f-droid.org/) private repo for Nym apps. This enables users to install and update Nym beta apps. As of December 2024, Nym [has applied](https://gitlab.com/fdroid/fdroiddata/-/merge_requests/17397) for inclusion in the F-Droid main repository. This private repo will remain active for beta and preview apps.

### Apps

<!-- This table is auto-generated. Do not edit -->
| Icon | Name | Description | Version |
| --- | --- | --- | --- |
| <a href=""><img src="fdroid/repo/cc47b0ee75e4f9bed164b5503a87417bd84c790b704098fcd11482535b80e2de/en-US/icon.png" alt="categories icon" width="36px" height="36px"></a> | [**categories**]() |  |  (2147483647) |
| <a href="https://github.com/nymtech/nym-vpn-client"><img src="fdroid/repo/net.nymtech.nymvpn/en-US/icon.png" alt="NymVPN icon" width="36px" height="36px"></a> | [**NymVPN**](https://github.com/nymtech/nym-vpn-client) | The NymVPN client apps for desktop and mobile | v1.1.5 (11500) |
<!-- end apps table -->

### How to install Nym apps
1. First, [install the F-Droid app](https://f-droid.org/). It's an alternative app store for Android.
2. In the app, navigate to Settings > Repositories and click the "+" floating action button.
3. To add the repository, click "SCAN QR CODE" and scan the QR code below or add the repository manually with the following URL:

    ```
    https://raw.githubusercontent.com/nymtech/fdroid/main/fdroid/repo?fingerprint=06C095C54BBFE147C986FD29ADF4E9BCD5E95ECACD6D865C6045B66B0B5500FB
    ```

    <p align="center">
      <img src=".github/qrcode.png?raw=true" alt="F-Droid repo QR code" width="300" height="300"/>
    </p>


4. You can now install Nym apps, e.g. start by searching for "NymVPN" in the F-Droid client.

Please note that some apps published here might contain [Anti-Features](https://f-droid.org/en/docs/Anti-Features/). If you can't find an app by searching for it, you can go to settings and enable "Include anti-feature apps".

### [License](LICENSE)
The license is for the files in this repository, *except* those in the `fdroid` directory. These files *might* be licensed differently; you can use an F-Droid client to get the details for each app.
