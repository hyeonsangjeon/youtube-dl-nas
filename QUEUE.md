# Work Queue

Active work is tracked in the public
[youtube-dl-nas Roadmap](https://github.com/users/hyeonsangjeon/projects/2).
The project board is the source of truth for priority, status, and target release.

## Completed For 26.0806

- Refresh history and activity after mobile foreground return or WebSocket reconnect.
- Prevent duplicate completed history rows for the same stored media.
- Add a signed per-device default profile for PWA mobile sharing.
- Guard playlist and channel downloads with explicit bounded or full scope.
- Save optional thumbnail sidecars and manage them with their media files.

## Completed For 26.0817

- Build Smart Share v2 with one-time iOS import setup, contextual profile, playlist, and timestamp choices, stable REST receipts, and Android profile parity.
- Show download-volume capacity and stop accepting new work at a configurable critical threshold.
- Stop the active yt-dlp process tree safely while preserving compatible partial data for retry.
- Classify failed jobs into privacy-safe reasons with a concrete recovery action in every supported language.
- Require a live container smoke test before Docker image publication and use bounded format fallbacks for less predictable sources.

## Completed For 26.0822

- Add a lightweight Library Overview to the existing history detail layer without a database or chart dependency.
- Guard public download submissions from private-network destinations by default, with an explicit trusted-source opt-in.
- Remember the last successfully queued dashboard profile on each device without automatic submission.
- Add explicit Compatible MP4 and Opus profiles while preserving existing profile behavior.
- Support optional Docker secret files for the login ID, password, and API token.
- Add authenticated, bounded Netscape cookies management while keeping external cookie mounts read-only.

Release details live in [CHANGELOG.md](CHANGELOG.md).
