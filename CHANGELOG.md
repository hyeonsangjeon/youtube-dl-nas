# Changelog

All notable changes to this project are documented here.

## Unreleased

### Documentation

- Added a dedicated Docker Hub overview with current screenshots, persistent-volume guidance, mobile sharing, multi-architecture tags, health checks, and release history.
- Added a reproducible, manually dispatched Docker Hub description workflow sourced from `DOCKERHUB.md`.

### Fixed

- Fixed the Android HTTP Shortcuts template prompting only for a password while leaving the NAS URL and login ID empty.
- Added a one-time **1. Configure NAS** shortcut that validates and stores the NAS URL, ID, and password before any download request is sent.
- Added clear setup and missing-URL errors, and normalized shared text to its first HTTP or HTTPS URL.
- Split raw Android share input from the JSON-encoded request URL so YouTube share data can be inspected before request-body encoding.
- Read both Android share title and text, with a manual URL prompt as a fallback for devices that omit the link from the share payload.

## 26.0710 - 2026-07-10

### Added

- Added an Android-installable PWA manifest with a Web Share Target for HTTPS deployments.
- Added an importable Android HTTP Shortcuts template for local HTTP NAS deployments.
- Added a signed, installable iOS Share Sheet shortcut with safe endpoint and credential placeholders.
- Added English and Korean mobile sharing guides prepared for GitHub Pages.
- Added optional Bearer authentication through `YDLNAS_API_TOKEN` while keeping ID/password REST authentication as the default.
- Added `compose.yaml` and `.env.example` with persistent download and application-state mounts.
- Added `/health` for container health checks.
- Added `PUID`, `PGID`, and `UMASK` container options.
- Added cookie-file and administrator-controlled extra argument support for `yt-dlp`.
- Added HTTP regression tests for login, REST authentication, queue protection, PWA assets, and share-target handling.

### Changed

- Preserved startup and hourly `yt-dlp` updates while isolating timeout and package-index failures from the application process.
- Persisted terms acceptance and the signed-cookie secret beside download history under the metadata volume.
- Unified dashboard and REST jobs through the same tracked worker so mobile/API downloads appear in activity and history.
- Reduced metadata extraction from three `yt-dlp` subprocesses to one JSON request.
- Replaced shell-based final-file moves with `yt-dlp` home/temp paths and an explicit post-processing filepath marker.
- Restricted queue and WebSocket endpoints to authenticated dashboard sessions.
- Added secure cookie attributes with optional HTTPS-only cookies.
- Simplified the container package set and removed unused legacy `youtube-dl` and `nlptutti` dependencies.
- Updated the runtime and CI baseline to Python 3.12 for current `yt-dlp` compatibility.
- Added Deno and matching `yt-dlp-ejs` components for current YouTube JavaScript challenge support, including hourly component updates.
- Added Docker image OCI labels, a persistent metadata volume, and a health check.
- Limited default-branch image builds to runtime-affecting paths.
- Polished README documentation for the `26.0710` mobile sharing and NAS installation release.

### Fixed

- Prevented empty REST credentials from matching an unconfigured account.
- Preserved a pending Android share target through terms acceptance and login.
- Changed the PWA share target to POST and kept pending URLs in a short-lived signed cookie instead of a side-effecting query string.
- Prevented a normal HTTP request to `/websocket` from dereferencing a missing WebSocket connection.
- Ignored unresolved `Auth.json` template placeholders during direct local execution.
- Standardized the MIT license text so repository metadata can identify it correctly.

## 26.0704 - 2026-07-04

### Changed

- Polished README documentation for the dashboard release, numbered history pages, explicit search, mounted file metadata states, and Docker publishing behavior.

### Added

- Added a logout route and dashboard logout button.
- Added mounted `/downfolder` file discovery so files that predate metadata history appear in the dashboard.
- Added explicit `No metadata` labels for mounted files discovered without saved history rows.
- Added a dashboard-style web UI for download management.
- Added a current activity panel with active download state, queue count, thumbnail, and progress.
- Added mobile history cards so the history view is usable without horizontal table scrolling.
- Added a history detail drawer with source URL, filename, UUID, downloaded time, size, and actions.
- Added history search, status/type filters, expanded sort options, and reset filters.
- Added numbered 20-item client-side history pages and an explicit history search button.
- Added `GET /youtube-dl/status` as a cookie-authenticated read-only dashboard status API.
- Added retry support for failed/error history rows.
- Added separate history-only delete and physical-file delete flows.
- Added refreshed README screenshots and an animated dashboard demo GIF.
- Added a GitHub Actions Docker workflow that validates pull requests and pushes images from release branches/tags.

### Changed

- Centralized the displayed app version as `26.0704` with an `APP_VERSION` environment override.
- Reloaded the file list after clearing saved history rows so kept files remain visible.
- Normalized history rows with stable metadata fields such as `timestamp`, `file_exists`, `file_size_bytes`, and `download_type`.
- Updated the dashboard JavaScript to keep table rows, mobile cards, and the detail drawer in sync from one history state.
- Improved responsive layout to prevent body-level horizontal overflow on mobile.
- Improved mobile history layout so card rows are shown without the desktop table.
- Compacted mobile history cards so long mounted filenames wrap cleanly and action buttons stay visible.
- Compacted the mobile history detail panel and scroll it into view after selecting a card.
- Updated cache-busting query strings for the dashboard CSS and JavaScript assets.
- Improved server-side download worker cleanup so failures do not leave the worker in a broken state.
- Fixed `run.sh` scheduler PID handling.
- Added `.dockerignore` to keep Git metadata, caches, and runtime history out of Docker build contexts.
- Updated the Dockerfile to create required runtime directories during image build.
- Updated the Dockerfile dependency install step so source-built Python packages can compile on slim ARM images without keeping build tools in the final layer.
- Reordered Dockerfile layers so Python dependency installation can be reused when only app code, docs, or screenshots change.

### Fixed

- Prevented invalid subtitle REST/API requests from being accepted without a language code.
- Fixed history clear behavior so it clears history rows without deleting downloaded files.
- Hardened file download serving by resolving files through normalized history metadata.
- Guarded dashboard JavaScript so it does not initialize on non-dashboard pages such as login.

## 25.0706 - 2025-07-06

### Added

- Added first-run Terms of Use agreement screen.
- Added subtitle download support.
- Added dynamic secret key generation for signed session cookies.
- Added copyright compliance guidance in the app flow.

### Changed

- Moved `download_history.json` to `./metadata/` for volume mount persistence.
- Updated `Auth.json` to include `TERMS_ACCEPTED` and `SECRET_KEY`.
- Improved Chrome download handling for filenames with special characters.

## 2025-06-13

### Changed

- Updated Python base version.
- Switched the download engine from `youtube-dl` to `yt-dlp`.
- Improved UI/UX and real-time progress display.
- Added optional proxy support.
- Added 2160p, 1440p, and audio-only download options.
- Added WebSocket queue updates.
- Improved HTTPS compatibility.

### Added

- Added file download and delete functionality from the UI.
- Added REST API for programmatic queueing.
- Added scheduled `yt-dlp` updates.

## Older Changes

- 2025-06-12: Kept selected options stable when clearing the URL input after submit.
- 2025-06-11: Added retry delay to handle transient network failures.
- 2023-02-19: Replaced `youtube-dl` with `yt-dlp` to resolve uploader extraction failures and improve speed.
- 2022-09-29: Added first-start package update checks.
- 2022-09-28: Cleared URL input after form submission.
- 2021-12-09: Fixed proxy settings.
- 2021-05-03: Fixed random MKV/MP4 format behavior when selecting resolution.
- 2020-11-13: Added Docker proxy environment support.
- 2020-08-12: Added MP3 audio option.
- 2020-04-07: Added audio-only support for web UI and REST calls.
- 2020-02-10: Improved HTTPS reverse-proxy compatibility.
- 2019-04-25: Added scheduled downloader update support in the Docker image.
- 2019-02-13: Rebuilt Docker image for downloader extractor errors.
- 2018-11-08: Improved YouTube short URL handling and Docker host-network app port support.
- 2018-10-06: Improved worker survival around WebSocket errors and added REST API.
- 2018-10-01: Fixed worker thread death during browser navigation and added 1440p/2160p options.
- 2018-09-28: Added selectable resolution and download result table.
