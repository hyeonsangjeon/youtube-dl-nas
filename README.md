# youtube-dl-nas

[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/modenaf360/youtube-dl-nas?style=flat-square)](https://hub.docker.com/r/modenaf360/youtube-dl-nas/)
[![Docker Stars](https://img.shields.io/docker/stars/modenaf360/youtube-dl-nas?style=flat-square)](https://hub.docker.com/r/modenaf360/youtube-dl-nas/)
[![Docker Image](https://github.com/hyeonsangjeon/youtube-dl-nas/actions/workflows/docker.yml/badge.svg)](https://github.com/hyeonsangjeon/youtube-dl-nas/actions/workflows/docker.yml)

`youtube-dl-nas` is a small NAS-friendly download queue for videos, audio, and subtitles. It wraps `yt-dlp` with an authenticated web dashboard, real-time progress updates, download history, file actions, and a REST API for automation.

![youtube-dl-nas dashboard demo](pic/dashboard-demo.gif)

Docker Hub: <https://hub.docker.com/r/modenaf360/youtube-dl-nas/>

Current release: `26.0710` (`2026-07-10`)

> **Need automatic full-channel backups instead?** `youtube-dl-nas` remains the
> small URL download queue. For scheduled channel backups, existing
> `archive.txt` and NAS-folder import, missing-only downloads, and disk-first
> recovery, see [Channel Vault NAS](https://github.com/hyeonsangjeon/channel-vault-nas).

| Choose | Best fit |
| --- | --- |
| **youtube-dl-nas** | Paste individual video/playlist URLs into a compact authenticated queue |
| **[Channel Vault NAS](https://github.com/hyeonsangjeon/channel-vault-nas)** | Register channels once and keep only missing/new videos backed up automatically |

## Highlights

- Queue video, audio, or subtitle downloads from a browser.
- Share a URL from an installed Android PWA, an Android HTTP Shortcut, or an iOS Shortcut workflow.
- Track current activity with queue count, progress, title, channel, and thumbnail.
- Review download history and mounted folder files with explicit search, filters, newest-first sorting, 20-item numbered pages, mobile cards, and a detail drawer.
- Surface pre-existing files in `/downfolder` even when they do not have saved download metadata.
- Retry failed items, download saved files, delete history rows, or delete physical files.
- Persist history, terms acceptance, and the signed-session secret under `./metadata`.
- Automate downloads through a simple REST API.
- Keep `yt-dlp` current at startup and every hour by default without stopping the app when an update check fails.
- Include Deno and the matching `yt-dlp-ejs` components required for current YouTube JavaScript challenges.
- Run cleanly on NAS or home-server Docker setups.

## Screenshots

<p>
  <img src="pic/dashboard-desktop.png" alt="youtube-dl-nas desktop dashboard" width="72%">
  <img src="pic/dashboard-mobile.png" alt="youtube-dl-nas mobile history cards" width="23%">
</p>

## Dashboard Workflow

1. Paste a URL, choose Video, Audio, or Subtitle mode, then submit it to the queue.
2. Watch the Current Activity panel for active progress, queue count, title, channel, thumbnail, and status.
3. Use Files & History to find completed downloads and mounted files. The default sort is newest downloaded first.
4. Search with the `Search` button or Enter, then move through results with 20-item page buttons.
5. Select a table row or mobile card to open file details, source URL, metadata state, and actions.

### Mounted Files And Metadata

Files already present in `/downfolder` are scanned into Files & History even if they were not downloaded by this app version. Those rows show `Mounted folder` and `No metadata` because source URL, channel, and quality details are not available.

Clearing history rows does not delete files. Kept files are reloaded from `/downfolder` and shown again as mounted files. Use the file delete action only when you want to remove the physical file.

## Quick Start

Docker Compose is the recommended installation because it preserves both downloads and application state:

```shell
cp .env.example .env
docker compose up -d
```

Edit `.env` before starting and set at least `MY_ID` and `MY_PW`. Downloads are stored in `./downloads`; history, terms acceptance, and the session secret are stored in `./config`.

The equivalent `docker run` command is:

```shell
docker run -d \
  --name youtube-dl-nas \
  --restart unless-stopped \
  -e MY_ID=nas-user \
  -e MY_PW=change-this-password \
  -v /volume2/youtube-dl:/downfolder \
  -v /volume2/docker/youtube-dl-nas:/usr/src/app/metadata \
  -p 8080:8080 \
  modenaf360/youtube-dl-nas
```

Open `http://localhost:8080`, sign in with `MY_ID` / `MY_PW`, accept the Terms of Use on first launch, and submit a URL.

### Time Zone

```shell
docker run -d \
  --name youtube-dl-nas \
  --restart unless-stopped \
  -e TZ=Asia/Seoul \
  -e MY_ID=nas-user \
  -e MY_PW=change-this-password \
  -v /volume2/youtube-dl:/downfolder \
  -v /volume2/docker/youtube-dl-nas:/usr/src/app/metadata \
  -p 8080:8080 \
  modenaf360/youtube-dl-nas
```

### Host Network With Custom App Port

```shell
docker run -d \
  --name youtube-dl-nas \
  --restart unless-stopped \
  --net=host \
  -e APP_PORT=9999 \
  -e MY_ID=nas-user \
  -e MY_PW=change-this-password \
  -v /volume2/youtube-dl:/downfolder \
  -v /volume2/docker/youtube-dl-nas:/usr/src/app/metadata \
  modenaf360/youtube-dl-nas
```

## Docker Options

| Option | Description |
| --- | --- |
| `-v host:/downfolder` | Required persistent download volume. Keep the guest path as `/downfolder`. |
| `-v host:/usr/src/app/metadata` | Recommended persistent configuration volume for history, terms acceptance, and session state. |
| `-p host:guest` | Port forwarding. The app defaults to `8080`. |
| `-e MY_ID` | Required login ID. Avoid values starting with `!`, `$`, or `&`. |
| `-e MY_PW` | Required login password. Avoid values starting with `!`, `$`, or `&`. |
| `-e TZ` | Optional container time zone, for example `Asia/Seoul`. |
| `-e APP_PORT` | Optional app port. Defaults to `8080`. |
| `-e PROXY` | Optional proxy value passed to `yt-dlp`. Defaults to empty. |
| `-e PUID`, `-e PGID` | Optional numeric owner for new download and state files. Defaults to `0`. |
| `-e UMASK` | Optional file creation mask. Defaults to `022`. |
| `-e YTDLP_AUTO_UPDATE` | Keep the startup and scheduled `yt-dlp` updater enabled. Defaults to `true`. |
| `-e YTDLP_UPDATE_INTERVAL` | Updater interval in seconds. Defaults to `3600`, with a minimum of `300`. |
| `-e YTDLP_COOKIES_FILE` | Optional path to a mounted Netscape-format cookies file. |
| `-e YTDLP_EXTRA_ARGS` | Optional administrator-controlled extra arguments parsed with shell-style quoting. |
| `-e YDLNAS_API_TOKEN` | Optional Bearer token for integrations. Normal ID/password API authentication remains available. |
| `-e COOKIE_SECURE` | Set to `true` when the dashboard is served exclusively over HTTPS. |

## Mobile Sharing

- Android over HTTPS: install the dashboard as a PWA, then select **youtube-dl NAS** from the Android share sheet.
- Android over local HTTP: import the provided HTTP Shortcuts template and enter the normal dashboard URL, ID, and password.
- iPhone/iPad: install the signed [Download to NAS Shortcut](docs/mobile/assets/Download-to-NAS.shortcut), replace its endpoint and credential placeholders, then share URLs directly to the NAS.

See the [mobile sharing guide](https://hyeonsangjeon.github.io/youtube-dl-nas/mobile/) or the source in [`docs/mobile`](docs/mobile/). No relay server is used; the phone sends URLs directly to the NAS. GitHub Pages only hosts the manual and import files.

## REST API

### Queue a Download

```shell
curl -X POST http://localhost:8080/youtube-dl/rest \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.youtube.com/watch?v=s9mO5q6GiAc",
    "resolution": "best",
    "id": "iamgroot",
    "pw": "1234"
  }'
```

Successful response:

```json
{
  "success": true,
  "msg": "download has started",
  "Remaining downloading count": "7"
}
```

The ID/password fields remain the default integration method. When `YDLNAS_API_TOKEN` is configured, advanced clients may omit them and send:

```shell
curl -X POST http://localhost:8080/youtube-dl/rest \
  -H 'Authorization: Bearer your-token' \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://youtu.be/s9mO5q6GiAc","resolution":"best"}'
```

Supported `resolution` examples:

- `best`
- `2160p`, `1440p`, `1080p`, `720p`, `480p`, `360p`, `240p`, `144p`
- `audio-m4a`, `audio-mp3`
- `vtt|en`, `vtt|ko`, `srt|en`, `srt|ko`

### Authenticated Dashboard APIs

These endpoints are used by the web UI and require a valid login cookie:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/youtube-dl/status` | `GET` | Read current active download, queue count, and connected clients. |
| `/youtube-dl/history` | `GET` | Read normalized download history plus mounted `/downfolder` files that are not in metadata yet. |
| `/youtube-dl/history/retry/<uuid>` | `POST` | Queue a previous history item again. |
| `/youtube-dl/history/delete/<uuid>` | `POST` | Delete the history row only. |
| `/youtube-dl/history/delete-file/<uuid>` | `POST` | Delete the physical file and related history rows. |
| `/youtube-dl/history/clear` | `POST` | Clear history rows while keeping downloaded files. |

## Local Development

Install dependencies:

```shell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Prepare `Auth.json` with local credentials, then run:

```shell
python youtube-dl-server.py
```

The app reads `APP_PORT` from `Auth.json`; the default is typically `8080` when substituted by the container entrypoint.

Useful checks before committing:

```shell
python3 -m py_compile youtube-dl-server.py
node --check static/logical_js/logic.js
pytest -q
docker compose --env-file .env.example config
git diff --check
docker build -t youtube-dl-nas:local .
```

## Container Build And Publishing

Build locally:

```shell
docker build -t youtube-dl-nas:local .
```

Run the local image:

```shell
docker run --rm \
  -e MY_ID=tester \
  -e MY_PW=secret \
  -v "$PWD/downfolder:/downfolder" \
  -v "$PWD/metadata:/usr/src/app/metadata" \
  -p 8080:8080 \
  youtube-dl-nas:local
```

The GitHub Actions workflow builds the Docker image for pull requests without publishing. Pushes to the default branch or version tags publish multi-architecture `linux/amd64` and `linux/arm64` images to both Docker Hub (`modenaf360/youtube-dl-nas`) and GHCR (`ghcr.io/hyeonsangjeon/youtube-dl-nas`), including `latest` on the default branch plus branch/tag and `sha-` tags.

Configure these repository secrets before publishing to Docker Hub:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

GHCR publishing uses the workflow's built-in `GITHUB_TOKEN`; no additional registry secret is required.

That keeps every Git change build-verified without publishing unreviewed images.

## Architecture

The application is a Python Bottle server running inside a Debian-based Python container. Browser and REST requests enter the same in-process worker queue, and completed files are written to `/downfolder`. A failure-isolated scheduler checks for current `yt-dlp` and matching EJS components at startup and hourly by default. Deno supplies the JavaScript runtime used by current YouTube extraction challenges.

- Web server: [`bottle`](https://github.com/bottlepy/bottle)
- WebSocket: [`bottle-websocket`](https://github.com/zeekay/bottle-websocket)
- Download engine: [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- Original queue server base: [`python queue server`](https://github.com/manbearwiz/youtube-dl-server)

<img src="pic/Architecture-Youtube-dl-nas.png" alt="youtube-dl-nas architecture" width="95%">

## Synology Notes

When using Synology Container Manager or Docker UI, mount a download folder to `/downfolder`, mount a configuration folder to `/usr/src/app/metadata`, and set `MY_ID`, `MY_PW`, and optional environment variables in the container settings. Use `compose.yaml` as a Container Manager project when available.

Volume setup:

![volume setting](pic/volume_set_synology.png)

ID and password setup:

![id password setting](pic/id_pw_set_synology.png)

## Legal Disclaimer

This tool is based on `yt-dlp` and is provided solely for personal and legitimate use in accordance with applicable laws. Users are responsible for complying with copyright laws. Downloading or distributing copyrighted material without permission from the rightsholder may violate applicable laws.

This project does not encourage or support unauthorized use. The developer bears no legal responsibility for unauthorized or illegal use by users.

## Release Notes

Full release history lives in [CHANGELOG.md](CHANGELOG.md).
