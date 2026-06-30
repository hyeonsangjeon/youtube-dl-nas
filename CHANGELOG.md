# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Added a dashboard-style web UI for download management.
- Added a current activity panel with active download state, queue count, thumbnail, and progress.
- Added mobile history cards so the history view is usable without horizontal table scrolling.
- Added a history detail drawer with source URL, filename, UUID, downloaded time, size, and actions.
- Added history search, status/type filters, expanded sort options, and reset filters.
- Added `GET /youtube-dl/status` as a cookie-authenticated read-only dashboard status API.
- Added retry support for failed/error history rows.
- Added separate history-only delete and physical-file delete flows.
- Added refreshed README screenshots and an animated dashboard demo GIF.
- Added a GitHub Actions Docker workflow that validates pull requests and pushes images from release branches/tags.

### Changed

- Normalized history rows with stable metadata fields such as `timestamp`, `file_exists`, `file_size_bytes`, and `download_type`.
- Updated the dashboard JavaScript to keep table rows, mobile cards, and the detail drawer in sync from one history state.
- Improved responsive layout to prevent body-level horizontal overflow on mobile.
- Improved mobile history layout so card rows are shown without the desktop table.
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
