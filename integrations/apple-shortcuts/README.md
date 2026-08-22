# Apple Shortcut

`Download-to-NAS.shortcut` is exported from Apple's Shortcuts app for installation by anyone and signed with Apple's `shortcuts` command-line tool.

Smart Share v2:

1. asks for the NAS base URL, dashboard ID, password, and default profile while it is imported;
2. accepts Share Sheet text or a URL, with a manual URL prompt when run without input;
3. uses the NAS context endpoint to identify playlists, channels, and YouTube timestamps;
4. asks only when the default profile is `ask`, a bulk scope is required, or a timestamp choice is available;
5. queues the resolved request with the existing ID/password REST authentication; and
6. displays the server's queue position or duplicate receipt.

No Shortcut action editing is required. Valid import profiles are `best`, `compatible-mp4`, `1080p`, `720p`, `audio-mp3`, `audio-m4a`, `audio-opus`, and `ask`. The distributed file contains placeholders only and no real endpoint or credentials.

`Download-to-NAS.plist` is the deterministic editable source. On macOS, regenerate and sign both installable copies with:

```shell
python3 integrations/apple-shortcuts/build_shortcut.py --sign
```
