# Apple Shortcut

`Download-to-NAS.shortcut` is exported from Apple's Shortcuts app for installation by anyone and signed with Apple's `shortcuts` command-line tool.

The shortcut:

1. accepts input from the iOS and iPadOS Share Sheet;
2. posts the shared URL to `http://NAS_ADDRESS:8080/youtube-dl/rest`;
3. requests `best` quality using the existing ID/password REST authentication; and
4. displays the server response.

Before using it, replace `NAS_ADDRESS`, `YOUR_ID`, and `YOUR_PASSWORD` inside the imported shortcut. The distributed file contains no real endpoint or credentials.
