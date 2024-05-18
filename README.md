# fdroid
This repository hosts an [F-Droid](https://f-droid.org/) repo for Nym apps. This allows users to install and update Nym apps very easily via.

### Apps

<!-- This table is auto-generated. Do not edit -->
| Name | Description | Version |
| --- | --- | --- |
| [**NymVPN**](https://github.com/nymtech/nym-vpn-android) | The NymVPN client app for Android | v1.0.2 (10200) |
<!-- end apps table -->

### How to use
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
