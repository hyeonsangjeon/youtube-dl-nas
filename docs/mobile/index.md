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

The installed PWA receives the shared URL. If your login expired, it asks you to sign in before adding the URL to the queue.

## Android On Local HTTP

Use the open-source [HTTP Shortcuts](https://http-shortcuts.rmy.ch/) app because Android cannot install a local HTTP site as a PWA.

1. Install HTTP Shortcuts.
2. [Import the youtube-dl-nas template](https://http-shortcuts.rmy.ch/import?url=https%3A%2F%2Fhyeonsangjeon.github.io%2Fyoutube-dl-nas%2Fmobile%2Fassets%2Fyoutube-dl-nas-http-shortcut.zip), or download the [ZIP file](assets/youtube-dl-nas-http-shortcut.zip) and import it manually.
3. Edit the imported global variables:
   - `nas_url`: your address without a trailing slash, such as `http://192.168.0.20:8080`
   - `nas_id`: your normal dashboard ID
   - `nas_password`: your normal dashboard password
4. Share a URL and select **Download to NAS**.

The REST API token is optional. The default template uses the same ID and password as the dashboard.

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
