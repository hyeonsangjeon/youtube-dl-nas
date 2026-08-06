---
layout: default
title: Mobile Share Setup
---

# Mobile Share Setup

[한국어](ko.html)

Mobile sharing sends a URL directly from your phone to the `youtube-dl-nas` instance running on your NAS. GitHub Pages only hosts this guide and the import files; it never receives your NAS address, ID, password, token, or shared URL.

## Android On HTTPS

1. Open your HTTPS `youtube-dl-nas` address in Chrome.
2. Sign in and accept the terms.
3. Choose **Install app** or **Add to Home screen** from Chrome's menu.
4. In YouTube, tap **Share**, then choose **youtube-dl NAS**.

The installed PWA receives the shared URL. In dashboard **Options**, choose Best, 1080p, 720p, MP3, M4A, or **Ask every time** as this device's mobile share default. Ask mode opens the composer with the URL filled in; the other profiles queue it immediately. If your login expired, sign in and the same flow continues without exposing the shared URL in the redirect.

Playlist and channel shares always open the composer so Playlist Guard can require an explicit First 10 or All items scope.

## Android On Local HTTP

Use the open-source [HTTP Shortcuts](https://http-shortcuts.rmy.ch/) app because Android cannot install a local HTTP site as a PWA.

1. Install HTTP Shortcuts.
2. [Import the youtube-dl-nas template](https://http-shortcuts.rmy.ch/import?url=https%3A%2F%2Fhyeonsangjeon.github.io%2Fyoutube-dl-nas%2Fmobile%2Fassets%2Fyoutube-dl-nas-http-shortcut.zip), or download the [ZIP file](assets/youtube-dl-nas-http-shortcut.zip) and import it manually.
3. Open the imported **youtube-dl NAS** category and run **1. Configure NAS** once.
4. Enter the full NAS address, normal dashboard ID, and password. For example, use `http://192.168.0.20:8080` for the address.
5. Share a URL and select **Download to NAS**. The saved settings are reused without asking again.

The REST API token is optional. The default template uses the same ID and password as the dashboard.

The shortcut checks both the Android share title and text. If the device omits the URL from that data, it opens a URL input as a fallback. Incomplete configuration stops before any network request is made.

## iPhone And iPad

The signed iOS shortcut uses the normal dashboard ID and password by default. [Download **Download to NAS.shortcut**](assets/Download-to-NAS.shortcut), open it in Shortcuts, and choose **Add Shortcut**.

1. Edit the imported shortcut.
2. Replace `http://NAS_ADDRESS:8080/youtube-dl/rest` with your NAS endpoint.
3. Replace `YOUR_ID` and `YOUR_PASSWORD` with your normal dashboard credentials.
4. In YouTube or Safari, tap **Share**, then choose **Download to NAS**.

The included shortcut accepts Share Sheet input and sends this JSON request directly to the NAS:

```json
{
  "url": "Shortcut Input",
  "resolution": "best",
  "id": "YOUR_ID",
  "pw": "YOUR_PASSWORD"
}
```

The file is exported for installation by anyone and signed through Apple's Shortcuts tooling. It contains placeholders only; no real NAS address or credentials are included. You can also recreate it manually with **Get Contents of URL** (`POST`, JSON body) and **Show Content**.

## Outside Your Home Network

Do not expose the plain HTTP port directly to the internet. Connect through a VPN such as Tailscale, or use an HTTPS reverse proxy on the NAS. Set `COOKIE_SECURE=true` when the dashboard is served exclusively through HTTPS.
