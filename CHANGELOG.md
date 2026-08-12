# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Added download-volume capacity status with configurable warning and critical thresholds; new queue requests pause before the mounted volume is exhausted.
- Added an authenticated active-download stop control that terminates the yt-dlp process group, retains compatible partial data, records a canceled row, and continues the queue.
- Added localized, actionable failure categories for authentication, rate limits, networking, storage, formats, extractors, and post-processing without persisting raw diagnostics.
- Added a Docker CI smoke job that starts the built image and verifies its live health and sign-in endpoints before publish jobs can run.
- Added Smart Share context discovery for mobile clients, including first-URL extraction, profile aliases, playlist or channel scope, and YouTube timestamp detection.
- Added a signed Smart Share v2 iOS Shortcut with one-time import questions, manual URL fallback, optional per-share profile selection, Playlist Guard choices, timestamp choices, and concise queue receipts.
- Added `section_mode=from_timestamp` support with persistent queue, restart, duplicate, history, and yt-dlp download-section handling.

### Changed

- Added bounded yt-dlp format fallbacks for video and audio profiles and removed full command, source URL, and mounted-path output from runtime logs.
- Return stable queued and duplicate receipt codes with the selected profile, queue position, and queue count from REST downloads.
- Let the Android HTTP Shortcuts setup save Best, 1080p, 720p, MP3, or M4A as its default profile and identify the client in REST requests.
- Keep an editable deterministic Apple Shortcut plist and builder beside the signed installable artifacts.

### Documentation

- Reworked the English and Korean mobile guides so iPhone and iPad setup no longer requires editing Shortcut actions.

## 26.0806 - 2026-08-06

### Added

- Added a per-device mobile share default with Best, 1080p, 720p, MP3, M4A, and Ask every time profiles.
- Added Playlist Guard with explicit Current video, First 10, and All items scopes for playlist and channel URLs.
- Added optional JPG thumbnail sidecars for video and audio downloads, authenticated local thumbnail previews, and sidecar-aware file deletion.

### Changed

- Persist playlist scope and thumbnail choices through the file-backed queue, restart recovery, queue display, and failed-job retry.
- Record each completed playlist output as its own history item using item-specific yt-dlp metadata.
- Publish `latest` and the pinned version tag together from one release-tag Docker build instead of rebuilding on both merge and tag pushes.

### Fixed

- Refresh history and activity when a mobile browser returns to the foreground or reconnects its WebSocket, without resetting filters, paging, or the selected item.
- Reuse an existing history row for the same physical file or extractor/media ID and preserve its original download timestamp.
- Keep thumbnail sidecars out of mounted-file rows and remove them with their associated media file.

### Documentation

- Updated the README, Docker Hub overview, dashboard guide, mobile sharing guide, and REST examples for the `26.0806` workflow.

## 26.0804 - 2026-08-04

### Added

- Added first-class internationalization for English, Korean, Simplified Chinese, and Polish across sign-in, terms, dashboard, queue, history, file actions, and Subtitle QA.
- Added language selectors before sign-in and in the authenticated dashboard, with a one-year preference cookie.
- Added stable API error codes and optional interpolation parameters while preserving existing English `msg` fields for REST compatibility.

### Changed

- Detect the first supported browser language on new devices and fall back to English for unsupported locales.
- Format dashboard dates, numbers, file sizes, status labels, and subtitle language names for the selected locale.
- Versioned the PWA cache for the localized application shell.

### Fixed

- Localized dynamic success, warning, validation, and download-failure messages that previously remained in English after switching languages.
- Prevented an internal terms-persistence error from being exposed in the browser response.

### Documentation

- Updated the dashboard manual and container tag examples for the multilingual `26.0804` release.

## 26.0731 - 2026-07-31

### Added

- Added a database-free safe queue that atomically persists the active request and waiting jobs under the metadata volume.
- Added restart recovery that restores the interrupted active request first and marks restored jobs in the dashboard.
- Added duplicate guards for normalized share URLs and stable extractor/media IDs, with an explicit REST force override.
- Added controls to remove waiting jobs before they become active.

### Changed

- Enabled explicit `yt-dlp --continue` behavior for compatible partial downloads.
- Exposed safe-queue persistence and restored-job counts through `/health`.

### Fixed

- Prevented shutdown from consuming the next waiting job or recording the interrupted active job as failed, while retaining it for restart recovery.
- Prevented different media with the same extracted title, especially Instagram Reels, from reusing an existing download by including the extractor and stable media ID in every new filename.
- Added the Reel ID to generic Instagram titles so separate downloads remain distinguishable in activity and history views.

### Documentation

- Added Awesome Selfhosted recognition to the leading README badges.
- Documented safe-queue persistence, restart recovery, duplicate handling, and waiting-job controls.

## 26.0714 - 2026-07-14

### Added

- Added authenticated Subtitle QA for downloaded or mounted SRT, VTT, ASS, and SSA files, with `nlptutti` CER, WER, CRR, edit counts, and keyword preservation results.
- Added a responsive Subtitle QA workflow to list, grid, card, and detail actions without exposing reference transcripts outside the NAS container.

### Changed

- Install or upgrade `nlptutti` once at new-container startup with an isolated timeout and keep the main download queue available if the package index cannot be reached.
- Report Subtitle QA availability and the installed `nlptutti` version from `/health`.

### Documentation

- Added English and Korean dashboard guides covering queue activity, list/grid history views, previews, mounted files, and container updates.
- Documented Subtitle QA usage, supported subtitle formats, runtime updater controls, and local-only transcript processing.

## 26.0713 - 2026-07-13

### Added

- Added compact list and thumbnail grid history views with persisted view preference, duration overlays, and graceful media-type placeholders when thumbnails are unavailable.
- Added authenticated inline video and audio previews for files already stored in `/downfolder`.
- Added an ordered **Up next** queue with request source and quality details, plus live transfer speed and ETA in Current Activity.
- Persisted thumbnail and duration metadata for newly completed, failed, and errored downloads.

### Changed

- Replaced the history type dropdown with a compact segmented filter that remains usable on mobile.
- Increased dashboard status polling frequency from ten to five seconds for faster queue and activity updates.
- Ignored local Python virtual environments used for development and tests.

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
