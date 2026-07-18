# Work Queue

## P1 - Refresh history when the mobile app returns to the foreground

### Problem

Mobile browsers can suspend the dashboard WebSocket while the share flow or a
download runs in the background. The server saves the completed history item
and its download timestamp, but the visible dashboard can remain stale until a
manual refresh or a later WebSocket reconnect.

### Scope

- Refresh `/youtube-dl/history` when the page becomes visible again through
  `visibilitychange` or `pageshow`.
- Refresh history after a WebSocket reconnect without resetting the selected
  view, filters, sort order, page, or detail item.
- Debounce overlapping foreground and reconnect refreshes.
- Keep the existing WebSocket completion update for active foreground sessions.

### Acceptance Criteria

- A download completed while the mobile browser is in the background appears
  with its download date when the user returns, without a manual refresh.
- Foreground refreshes do not duplicate history rows or move the user away from
  the current filtered view unnecessarily.
- Network failures leave the existing history visible and allow the next
  foreground or reconnect refresh to retry.
- The behavior is covered by focused JavaScript or browser regression tests.

## P1 - Prevent duplicate history for the same downloaded media

### Problem

Submitting the same media repeatedly can create multiple completed history rows
that point to the same existing file. Each row receives a new completion time
even when `yt-dlp` reused the file instead of downloading it again.

### Scope

- Identify media by `extractor` plus `media_id`, with normalized source URL and
  final filepath as fallbacks when extractor metadata is unavailable.
- When a completed record already points to the same existing file, update or
  reuse that record instead of appending another completed row.
- Preserve the timestamp of the actual file download when `yt-dlp` skips an
  already-downloaded file.
- Allow a genuinely new download after the previous physical file was deleted.
- Return a clear `Already downloaded` result for repeated submissions where
  practical.

### Acceptance Criteria

- Repeating the same Instagram Reel, YouTube video, or other stable media ID
  does not create duplicate completed rows for one physical file.
- The displayed download date represents the actual stored file, not the time
  of a skipped duplicate request.
- Different media with the same title remain separate records.
- Duplicate detection is covered by server regression tests.
