"""Bounded, local subtitle search and conservative media/sidecar association."""

import base64
import hashlib
import html
import json
import math
import os
import re
import sys
import unicodedata
from collections import OrderedDict
from datetime import date
from threading import RLock
from urllib.parse import quote

import pysubs2

from collections_backend import APIError, library_page, open_media_file


SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa"}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_CUES = 20000
MAX_CUE_CHARS = 4000
MAX_SCAN_FILES = 100
MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_TRANSCRIPT_CHARS = 20000
LANGUAGE_SUFFIX = re.compile(r"\.[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*(?:-orig)?$")


def normalized_text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def media_identity(item):
    if not item.get("media_id") or not item.get("extractor"):
        return None
    try:
        start = float(item.get("section_start") or 0)
        if not math.isfinite(start) or start < 0:
            return None
    except (TypeError, ValueError):
        return None
    return (
        str(item["extractor"]).casefold(), str(item["media_id"]),
        item.get("section_mode") or "full", start,
    )


def related_media(subtitle, items):
    """Never infer identity from display titles or cross-directory basenames."""
    path = subtitle.get("relative_path") or ""
    stem = os.path.splitext(path)[0]
    candidates = [item for item in items if item.get("file_exists")
                  and item.get("download_type") in {"video", "audio"}]
    identity = media_identity(subtitle)
    if identity:
        matches = [item for item in candidates if media_identity(item) == identity]
    else:
        stems = {stem, LANGUAGE_SUFFIX.sub("", stem)}
        matches = [item for item in candidates
                   if os.path.splitext(item.get("relative_path") or "")[0] in stems
                   and (item.get("section_mode") or "full") == "full"]
    # Multiple resolutions or copies are ambiguous; do not choose one silently.
    by_path = {item["relative_path"]: item for item in matches}
    return next(iter(by_path.values())) if len(by_path) == 1 else None


def public_media(item):
    if item is None:
        return None
    item_id = str(item["uuid"])
    mounted = item.get("source") == "mounted_folder" or item.get("metadata_status") == "missing"
    return {
        key: item.get(key) for key in (
            "uuid", "title", "channel", "filename", "relative_path", "timestamp",
            "file_exists", "file_size_bytes", "download_type", "status", "url",
        )
    } | {
        "timestamp_kind": "modified" if mounted else "downloaded",
        "detail_url": "/youtube-dl?item=" + quote(item_id, safe=""),
    }


def media_files(item, items):
    selected = {item.get("relative_path"): item}
    anchor = related_media(item, items) if item.get("download_type") == "subtitle" else item
    if anchor and anchor.get("download_type") in {"video", "audio"}:
        selected[anchor.get("relative_path")] = anchor
        for other in items:
            if other.get("file_exists") and other.get("download_type") == "subtitle":
                linked = related_media(other, items)
                if linked and linked.get("relative_path") == anchor.get("relative_path"):
                    selected[other.get("relative_path")] = other
    return {"item": public_media(item), "files": [public_media(value) for value in selected.values()]}


class SubtitleSearch:
    def __init__(self, cache_bytes=16 * 1024 * 1024, cache_files=64):
        self.cache = OrderedDict()
        self.cache_bytes = cache_bytes
        self.cache_files = cache_files
        self.cache_size = 0
        self.lock = RLock()

    def _read(self, root, item, budget=None):
        relative = item.get("relative_path") or ""
        extension = os.path.splitext(relative)[1].lower()
        if extension not in SUBTITLE_EXTENSIONS:
            raise APIError("subtitle_format_unsupported", 422)
        # Open safely even on a cache hit: symlink replacement must not serve cached text.
        with self.lock, open_media_file(root, relative) as source:
            info = os.fstat(source.fileno())
            signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if info.st_size > MAX_FILE_BYTES:
                raise APIError("subtitle_file_too_large", 422)
            read_limit = min(MAX_FILE_BYTES, budget["remaining"]) if budget is not None else MAX_FILE_BYTES
            if info.st_size > read_limit:
                raise APIError("search_page_full")
            key = (os.path.abspath(root), relative)
            cached = self.cache.pop(key, None)
            if cached:
                self.cache_size -= cached[3]
                if cached[0] == signature:
                    self.cache[key] = cached
                    self.cache_size += cached[3]
                    if budget is not None:
                        budget["remaining"] -= info.st_size
                    return cached[1], cached[2], info.st_size
            content = source.read(read_limit + 1)
            if budget is not None:
                budget["remaining"] -= min(len(content), read_limit)
            if len(content) > MAX_FILE_BYTES:
                raise APIError("subtitle_file_too_large", 422)
            if len(content) > read_limit:
                raise APIError("search_page_full")
            try:
                text = content.decode("utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
                parsed = pysubs2.SSAFile.from_string(text, format_=extension[1:])
            except (UnicodeError, ValueError, pysubs2.exceptions.Pysubs2Error):
                raise APIError("subtitle_file_read_failed", 422) from None
            cues = []
            truncated = len(parsed) > MAX_CUES
            for event in parsed[:MAX_CUES]:
                if event.is_comment or event.start < 0 or event.end < event.start:
                    continue
                text = " ".join(html.unescape(event.plaintext).split())
                if not text:
                    continue
                truncated = truncated or len(text) > MAX_CUE_CHARS
                text = text[:MAX_CUE_CHARS]
                cues.append((event.start / 1000, event.end / 1000, text, normalized_text(text)))
            cost = sys.getsizeof(cues) + sum(sys.getsizeof(cue) + sum(sys.getsizeof(part) for part in cue) for cue in cues)
            while self.cache and (self.cache_size + cost > self.cache_bytes or len(self.cache) >= self.cache_files):
                self.cache_size -= self.cache.popitem(last=False)[1][3]
            if cost <= self.cache_bytes:
                self.cache[key] = (signature, cues, truncated, cost)
                self.cache_size += cost
            return cues, truncated, info.st_size

    @staticmethod
    def _date_bounds(date_from, date_to):
        try:
            for value in (date_from, date_to):
                if value and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or date.fromisoformat(value).isoformat() != value):
                    raise ValueError()
            if date_from and date_to and date_from > date_to:
                raise ValueError()
        except (TypeError, ValueError):
            raise APIError("invalid_date_range") from None

    def search(self, root, items, query, *, limit=20, cursor=None, date_from="", date_to=""):
        query = normalized_text(query)
        if not query or len(query) > 200:
            raise APIError("invalid_search_query")
        if not 1 <= limit <= 50:
            raise APIError("invalid_limit")
        self._date_bounds(date_from, date_to)
        files = []
        seen = set()
        for item in library_page(items, limit=len(items))["items"]:
            relative = item.get("relative_path") or ""
            if (not item.get("file_exists") or os.path.splitext(relative)[1].lower() not in SUBTITLE_EXTENSIONS
                    or relative in seen):
                continue
            seen.add(relative)
            timestamp = str(item.get("timestamp") or "")[:10]
            if (date_from and timestamp < date_from) or (date_to and (not timestamp or timestamp > date_to)):
                continue
            files.append(item)
        context = hashlib.sha256(json.dumps([
            query, date_from, date_to,
            [(item["uuid"], item.get("timestamp"), item.get("relative_path"), item.get("file_size_bytes")) for item in files],
        ], ensure_ascii=True).encode()).hexdigest()
        offset = 0
        if cursor:
            try:
                if len(cursor) > 512:
                    raise ValueError()
                page = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                offset = page["offset"]
                if type(offset) is not int or not 0 <= offset <= len(files):
                    raise ValueError()
                if page["context"] != context:
                    raise APIError("search_changed", 409)
            except APIError:
                raise
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise APIError("invalid_cursor") from None
        results, scanned, skipped, truncated_files = [], 0, 0, 0
        budget = {"remaining": MAX_SCAN_BYTES}
        while offset < len(files) and len(results) < limit and scanned < MAX_SCAN_FILES and budget["remaining"] > 0:
            item = files[offset]
            offset += 1
            scanned += 1
            try:
                cues, truncated, _ = self._read(root, item, budget)
            except APIError as error:
                if error.code == "search_page_full":
                    offset -= 1
                    scanned -= 1
                    break
                skipped += 1
                continue
            except OSError:
                skipped += 1
                continue
            truncated_files += int(truncated)
            matches = []
            for index, (start, end, text, normalized) in enumerate(cues):
                if query in normalized:
                    matches.append({"cue": index, "start": start, "end": end, "text": text})
                    if len(matches) == 3:
                        break
            if matches:
                results.append({
                    "subtitle": public_media(item), "media": public_media(related_media(item, items)),
                    "matches": matches, "truncated": truncated,
                })
        next_cursor = None
        if offset < len(files):
            next_cursor = base64.urlsafe_b64encode(json.dumps({"offset": offset, "context": context}).encode()).decode()
        return {
            "items": results, "has_more": bool(next_cursor), "next_cursor": next_cursor,
            "scanned": scanned, "scanned_through": offset, "subtitle_files": len(files),
            "skipped": skipped, "truncated_files": truncated_files,
            "local_only": True,
        }

    def transcript(self, root, item, *, offset=0, limit=40):
        if offset < 0 or not 1 <= limit <= 100:
            raise APIError("invalid_limit")
        cues, truncated, _ = self._read(root, item)
        if offset > len(cues):
            raise APIError("invalid_offset")
        selected, characters = [], 0
        for index in range(offset, min(offset + limit, len(cues))):
            start, end, text, _ = cues[index]
            if selected and characters + len(text) > MAX_TRANSCRIPT_CHARS:
                break
            selected.append({"cue": index, "start": start, "end": end, "text": text})
            characters += len(text)
        next_offset = offset + len(selected)
        return {
            "subtitle": public_media(item), "cues": selected, "total_cues": len(cues),
            "next_offset": next_offset if next_offset < len(cues) else None,
            "truncated": truncated,
        }
