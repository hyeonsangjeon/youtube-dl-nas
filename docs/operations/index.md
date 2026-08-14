---
layout: default
title: Install, Upgrade, and Troubleshoot
---

# Install, Upgrade, and Troubleshoot

This is the operational path for a normal Docker or NAS installation. It keeps
downloads and application state outside the container so an image update does
not discard either one.

## Install With Docker Compose

Docker Compose is the recommended deployment method.

```shell
git clone https://github.com/hyeonsangjeon/youtube-dl-nas.git
cd youtube-dl-nas
cp .env.example .env
```

Edit `.env` and set at least `MY_ID` and `MY_PW`. Review these paths before the
first start:

- `DOWNLOAD_DIR` stores completed and partial media.
- `CONFIG_DIR` stores queue state, history, terms acceptance, and session data.
- `WEB_PORT` exposes the dashboard and defaults to `8080`.

Validate and start the deployment:

```shell
docker compose config
docker compose pull
docker compose up -d
docker compose ps
```

Open `http://<nas-address>:<WEB_PORT>` and sign in with the configured ID and
password. Use HTTPS before exposing the dashboard outside a trusted network.

## Upgrade

Back up or snapshot `DOWNLOAD_DIR` and `CONFIG_DIR` before changing an image or
deployment configuration. Then update the checked-out deployment and recreate
the container:

```shell
git pull --ff-only
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 youtube-dl-nas
```

The default Compose file follows `modenaf360/youtube-dl-nas:latest`. To control
upgrade timing, replace `latest` in `compose.yaml` with a tag from the
[release page](https://github.com/hyeonsangjeon/youtube-dl-nas/releases) and
run the same pull and up commands. Keep both persistent mounts unchanged.

## Troubleshooting Checklist

### Container Does Not Start

Validate resolved settings and inspect recent logs:

```shell
docker compose config
docker compose ps
docker compose logs --tail=200 youtube-dl-nas
```

Confirm that `MY_ID` and `MY_PW` are set in `.env` and that another service is
not already using `WEB_PORT`.

### Downloads Or State Disappear

Confirm the host paths behind `/downfolder` and `/usr/src/app/metadata` still
point to the intended persistent directories. The first mount holds media; the
second holds queue and history state. Recreating a container is safe only when
both mounts are preserved.

Inspect the mounted paths and available space:

```shell
docker compose exec youtube-dl-nas sh -lc \
  'id; df -h /downfolder /usr/src/app/metadata; ls -ld /downfolder /usr/src/app/metadata'
```

If the directories are not writable, align `PUID`, `PGID`, and host-folder
permissions with the account that owns the mounted paths.

### A Source Stops Downloading

Pull the newest image first. The container also updates `yt-dlp` at startup and
on its configured schedule, but some sources can still require cookies, a
proxy, or a later upstream extractor fix. Check `YTDLP_COOKIES_FILE`, `PROXY`,
and `YTDLP_EXTRA_ARGS` only when the source requires them.

Do not post private URLs, cookies, passwords, API tokens, or complete browser
headers in logs or issues.

### Login Or Mobile Sharing Fails

Use the full dashboard base URL, including the port and any reverse-proxy path.
Set `COOKIE_SECURE=true` only when the dashboard is served exclusively over
HTTPS. Mobile shares travel directly from the phone to the NAS; GitHub Pages
hosts only the setup guide and import files.

See the [mobile sharing guide](../mobile/) for Android PWA, Android local HTTP,
and iPhone/iPad setup.

## Report A Reproducible Problem

Search [existing issues](https://github.com/hyeonsangjeon/youtube-dl-nas/issues)
before opening a new report. If the problem remains, use the
[bug report form](https://github.com/hyeonsangjeon/youtube-dl-nas/issues/new?template=bug.yml)
and include:

- image tag or release version
- NAS platform and deployment method
- concise reproduction steps and expected behavior
- sanitized logs with credentials and private URLs removed

For feature ideas, use the
[feature request form](https://github.com/hyeonsangjeon/youtube-dl-nas/issues/new?template=feature.yml).
