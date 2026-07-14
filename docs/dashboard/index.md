---
layout: default
title: Dashboard Guide
---

# Dashboard Guide

[한국어](ko.html)

The authenticated dashboard manages individual video, audio, and subtitle downloads on your NAS.

## New Download

1. Choose **Video**, **Audio**, or **Subtitle**.
2. Select the quality or subtitle language.
3. Paste a supported URL and select **Submit**.

## Current Activity

The activity panel shows the active title, channel, thumbnail, progress, transfer speed, and ETA. **Up next** lists waiting requests in processing order with their source and selected quality.

## Files And History

- Switch between **List** and **Grid**. The selected view is remembered in the browser.
- Search titles, channels, filenames, and metadata states.
- Filter by status or media type. Downloads are newest first by default.
- Move through results in numbered pages of 20 items.
- Select an item to inspect its source URL, duration, resolution, size, filename, metadata state, and UUID.

Use **Preview** to play an existing video or audio file without downloading it again. Other actions can retry a failed job, download the saved file, remove only its history row, or delete the physical file.

## Subtitle QA

For an available SRT, VTT, ASS, or SSA file, select **Subtitle QA** from the item actions. Paste the verified reference transcript and optionally add comma- or line-separated keywords, then select **Analyze**.

The result reports character accuracy (CRR), character error rate (CER), word error rate (WER), character edit counts, and keyword preservation. The selected file and reference text remain inside the NAS container. `nlptutti` is installed or upgraded when a new container starts so the analyzer follows current package releases.

## Mounted Files

Files already present in `/downfolder` are discovered automatically. When no saved download record exists, the dashboard labels the item **Mounted** and **No metadata**. The file remains available for preview, browser download, and deletion, but its original source URL and quality cannot be reconstructed.

Clearing history rows does not delete physical files. Kept files are discovered again as mounted files.

## Update The Container

```shell
docker compose pull
docker compose up -d
```

The `latest` and `26.0713` images support `linux/amd64` and `linux/arm64`.

For phone sharing, continue to the [Mobile Share Setup](../mobile/).
