# Deployment Paths

Use the canonical files and guides below to deploy `youtube-dl-nas`. The root
Compose configuration is validated by CI, so these links stay aligned with the
current image and supported environment variables.

## Docker Compose

Recommended for most NAS and home-server installations:

1. Copy [`.env.example`](../.env.example) to `.env` and set `MY_ID` and `MY_PW`.
2. Review [`compose.yaml`](../compose.yaml), especially `DOWNLOAD_DIR` and
   `CONFIG_DIR`.
3. Follow the [Quick Start](../README.md#quick-start).

The download directory and metadata directory are separate persistent mounts.
Keep both when recreating or upgrading the container.

## Docker CLI

Use the maintained [`docker run` example](../README.md#quick-start) when Docker
Compose is unavailable. Reuse the same `/downfolder` and
`/usr/src/app/metadata` mounts whenever the container is replaced.

## Synology Container Manager

Use the [Synology notes](../README.md#synology-notes) for volume, environment,
and port settings. Importing [`compose.yaml`](../compose.yaml) as a Container
Manager project is preferred when the NAS supports projects.

## Operate And Upgrade

The [operations guide](https://hyeonsangjeon.github.io/youtube-dl-nas/operations/)
covers first installation, upgrades, persistent data, logs, common failures,
and safe issue reporting.

For phone-to-NAS setup, use the
[mobile sharing guide](https://hyeonsangjeon.github.io/youtube-dl-nas/mobile/).
