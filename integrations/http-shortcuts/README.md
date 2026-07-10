# Android HTTP Shortcut

This template lets Android send a shared URL directly to a local `youtube-dl-nas` REST endpoint, including plain HTTP addresses that cannot install a PWA.

1. Install [HTTP Shortcuts](https://http-shortcuts.rmy.ch/).
2. Import `youtube-dl-nas-http-shortcut.zip` from this directory or its GitHub Release asset.
3. Open the imported **youtube-dl NAS** category and run **1. Configure NAS** once.
4. Enter the full NAS URL, login ID, and password when prompted. For example, use `http://192.168.0.20:8080` for the URL.
5. Share a URL from YouTube or a browser and select **Download to NAS**. Saved settings are reused without prompting again.

If the settings are incomplete, **Download to NAS** stops before making a request and asks you to run **1. Configure NAS**. The shortcut checks both the Android share title and text, then sends the first HTTP or HTTPS URL to the NAS. On devices that omit the URL from the share payload, it opens a URL input as a fallback.

The exported template deliberately contains no server address or credentials. The configuration shortcut stores them only in the HTTP Shortcuts app on the phone. Android 11 and newer can show the imported launcher shortcut as a Direct Share target.
