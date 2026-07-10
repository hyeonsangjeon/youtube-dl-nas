# Android HTTP Shortcut

This template lets Android send a shared URL directly to a local `youtube-dl-nas` REST endpoint, including plain HTTP addresses that cannot install a PWA.

1. Install [HTTP Shortcuts](https://http-shortcuts.rmy.ch/).
2. Import `youtube-dl-nas-http-shortcut.zip` from this directory or its GitHub Release asset.
3. Open Global Variables and fill `nas_url`, `nas_id`, and `nas_password`.
4. Keep `nas_url` free of a trailing slash, for example `http://192.168.0.20:8080`.
5. Share a URL from YouTube or a browser and select **Download to NAS**.

The exported template deliberately contains no server address or credentials. Android 11 and newer can show the imported launcher shortcut as a Direct Share target.
