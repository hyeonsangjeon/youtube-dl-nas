import json
import os
from pathlib import Path

import pytest
from bottle import default_app
from webtest import TestApp

import library_search as search
from collections_backend import APIError, ConnectionStore, StateError
from test_collections import (
    AUTH, BASE, approve, client, finish_job, isolated_backend, login, make_plan,
)
from test_server import server, stable_public_source_network


def subtitle_file(root, name="lesson.en.srt", text="Agent memory stays on the NAS.", **metadata):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n00:00:12,500 --> 00:00:15,000\n" + text + "\n\n2\n00:00:16,000 --> 00:00:19,000\nSecond sentence.\n")
    return dict(uuid=name.replace(".", "-"), relative_path=name, filename=path.name,
                title="Lesson", timestamp="2026-11-05T14:00:00", file_exists=True,
                file_size_bytes=path.stat().st_size, download_type="subtitle", **metadata)


def test_search_reads_cues_and_related_video_without_display_title_matching(tmp_path):
    subtitle = subtitle_file(tmp_path)
    video = dict(uuid="video", relative_path="lesson.mp4", file_exists=True, download_type="video")
    unrelated = dict(uuid="unrelated", title="Lesson", relative_path="another.mp4", file_exists=True, download_type="video")
    result = search.SubtitleSearch().search(tmp_path, [subtitle, video, unrelated], "AGENT memory")
    assert result["local_only"] and not result["has_more"]
    match = result["items"][0]
    assert match["media"]["uuid"] == "video"
    assert match["matches"][0]["start"] == 12.5
    assert match["subtitle"]["timestamp_kind"] == "downloaded"
    assert search.related_media(subtitle, [unrelated]) is None
    assert search.related_media(subtitle, [video, dict(video, uuid="other", relative_path="lesson.webm")]) is None
    assert search.related_media(subtitle, [dict(video, relative_path="other/lesson.mp4")]) is None


def test_identity_links_different_names_but_never_different_clips(tmp_path):
    subtitle = subtitle_file(tmp_path, media_id="abc", extractor="Youtube")
    video = dict(uuid="video", relative_path="different.mp4", file_exists=True, download_type="video",
                 media_id="abc", extractor="youtube")
    assert search.related_media(subtitle, [video]) == video
    assert search.related_media(subtitle, [dict(video, section_mode="from", section_start=10)]) is None


@pytest.mark.parametrize("extension,content", [
    ("vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<b>기억 ＡＢＣ</b> &amp; café\n"),
    ("ass", "[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,기억 ＡＢＣ & café\n"),
])
def test_supported_formats_and_unicode(tmp_path, extension, content):
    item = subtitle_file(tmp_path, name="lesson." + extension)
    (tmp_path / item["relative_path"]).write_text(content)
    result = search.SubtitleSearch().search(tmp_path, [item], "기억 abc")
    assert result["items"][0]["matches"][0]["start"] == 1
    assert "<b>" not in result["items"][0]["matches"][0]["text"]


def test_search_pagination_date_bounds_and_changed_library(tmp_path, monkeypatch):
    items = [subtitle_file(tmp_path, name=f"lesson{i}.srt") for i in range(3)]
    engine = search.SubtitleSearch()
    first = engine.search(tmp_path, items, "memory", limit=1)
    second = engine.search(tmp_path, items, "memory", limit=1, cursor=first["next_cursor"])
    assert first["items"][0]["subtitle"]["uuid"] != second["items"][0]["subtitle"]["uuid"]
    assert engine.search(tmp_path, items, "memory", date_from="2026-11-06")["items"] == []
    with pytest.raises(APIError, match="invalid_date_range"):
        engine.search(tmp_path, items, "memory", date_from="2026-02-31")
    with pytest.raises(APIError, match="search_changed"):
        engine.search(tmp_path, items[:1], "memory", cursor=first["next_cursor"])
    monkeypatch.setattr(search, "MAX_SCAN_FILES", 1)
    no_match = engine.search(tmp_path, items, "absent")
    assert not no_match["items"] and no_match["has_more"]


def test_cache_refreshes_file_and_refuses_symlink_and_oversized_input(tmp_path):
    engine = search.SubtitleSearch(cache_files=1, cache_bytes=4096)
    item = subtitle_file(tmp_path)
    assert engine.search(tmp_path, [item], "memory")["items"]
    subtitle_file(tmp_path, text="Different topic")
    assert not engine.search(tmp_path, [item], "memory")["items"]
    path = tmp_path / item["relative_path"]
    path.unlink()
    secret = tmp_path / "private.txt"
    secret.write_text("1\n00:00:01,000 --> 00:00:02,000\nprivate memory\n")
    path.symlink_to(secret)
    assert engine.search(tmp_path, [item], "private")["skipped"] == 1
    path.unlink()
    path.write_bytes(b"x" * (search.MAX_FILE_BYTES + 1))
    assert engine.search(tmp_path, [item], "x")["skipped"] == 1
    assert engine.cache_size <= 4096


def test_scan_budget_continues_before_reading_the_next_file(tmp_path, monkeypatch):
    items = [subtitle_file(tmp_path, name=f"lesson{i}.srt") for i in range(3)]
    size = items[0]["file_size_bytes"]
    monkeypatch.setattr(search, "MAX_SCAN_BYTES", size * 2 - 1)
    engine = search.SubtitleSearch()
    first = engine.search(tmp_path, items, "memory")
    assert len(first["items"]) == first["scanned"] == 1
    second = engine.search(tmp_path, items, "memory", cursor=first["next_cursor"])
    assert len(second["items"]) == 1
    assert first["items"][0]["subtitle"]["uuid"] != second["items"][0]["subtitle"]["uuid"]
    assert engine.search(tmp_path, items, "memory")["scanned"] == 1  # Cached reads keep the same budget.
    for item in items:
        (tmp_path / item["relative_path"]).write_bytes(b"\x80" * size)
    failed = engine.search(tmp_path, items, "memory")
    assert failed["skipped"] == failed["scanned"] == 1 and failed["has_more"]


def test_transcript_is_paged_and_limit_is_validated(tmp_path):
    engine = search.SubtitleSearch()
    item = subtitle_file(tmp_path)
    first = engine.transcript(tmp_path, item, limit=1)
    assert first["next_offset"] == 1
    assert engine.transcript(tmp_path, item, offset=1)["next_offset"] is None
    with pytest.raises(APIError):
        engine.transcript(tmp_path, item, offset=-1)
    with pytest.raises(APIError):
        engine.search(tmp_path, [item], " ")


def test_search_only_token_reads_but_cannot_write_or_use_legacy_routes(client, isolated_backend):
    downloads, _ = isolated_backend
    item = subtitle_file(downloads)
    item_id = server.get_mounted_file_uuid(item["relative_path"])
    login(client)
    created = client.post_json(BASE + "/connections", {"name": "Read only", "access": "search"}).json
    headers = {"Authorization": "Bearer " + created["token"]}
    reader = TestApp(default_app())
    result = reader.get(BASE + "/library/search", {"q": "memory"}, headers=headers).json
    assert result["items"][0]["subtitle"]["uuid"] == item_id
    assert reader.get(BASE + f"/library/{item_id}/transcript", headers=headers).json["cues"]
    for path in ("/downloads", "/plans", "/plans/fake/commit"):
        assert reader.post_json(BASE + path, {}, headers=headers, status=403).json["code"] == "read_only_connection"
    reader.get(BASE + "/downloads", headers=headers, status=403)
    reader.get("/youtube-dl/history", headers=headers, status=403)
    reader.get("/static/downfolder/" + item_id, headers=headers, status=403)
    # An admin browser cookie must not elevate an explicitly supplied scoped token.
    client.post_json(BASE + "/downloads", {}, headers=headers, status=403)
    client.post_json(BASE + "/connections", {"name": "Elevate"}, headers=headers, status=401)
    client.delete(BASE + "/connections/" + created["connection"]["id"])
    reader.get(BASE + "/library/search", {"q": "memory"}, headers=headers, status=401)


def test_collection_scope_cannot_read_other_files_or_collections(client, isolated_backend):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    job = server.get_queued_downloads()[0]
    # Complete an actual subtitle membership, then add a separate private file.
    finish_job(downloads, job, "member.srt")
    relative = job["target_relative_directory"] + "/member.srt"
    subtitle_file(downloads, relative)
    subtitle_file(downloads, "private.srt", text="Private memory")
    login(client)
    connection = client.post_json(BASE + "/connections", {
        "name": "Collection only", "access": "search", "collection_ids": [first["collection"]["id"]],
    }).json
    headers = {"Authorization": "Bearer " + connection["token"]}
    reader = TestApp(default_app())
    result = reader.get(BASE + "/library/search", {"q": "memory"}, headers=headers).json
    assert len(result["items"]) == 1
    private_id = server.get_mounted_file_uuid("private.srt")
    reader.get(BASE + f"/library/{private_id}/transcript", headers=headers, status=404)
    reader.get(BASE + f"/library/{private_id}/files", headers=headers, status=404)
    reader.get(BASE + "/collections/not-allowed", headers=headers, status=404)
    assert len(reader.get(BASE + "/collections", headers=headers).json["collections"]) == 1


def test_invalid_connection_permissions_fail_closed(client):
    login(client)
    for body in ({"access": []}, {"access": "admin"}, {"access": "search", "collection_ids": []}):
        client.post_json(BASE + "/connections", {"name": "Invalid", **body}, status=400)


def test_http_query_decodes_non_ascii_search_text(client, isolated_backend):
    downloads, _ = isolated_backend
    subtitle_file(downloads, "기억.srt", text="기억과 메모리 café")
    for query in ("기억", "café"):
        result = client.get(BASE + "/library/search", {"q": query}, headers=AUTH).json
        assert len(result["items"]) == 1
    assert len(client.get(BASE + "/library", {"q": "기억"}, headers=AUTH).json["items"]) == 1


def test_legacy_connection_state_keeps_existing_permissions(tmp_path):
    store = ConnectionStore(str(tmp_path / "connections.json"))
    result = store.create("Existing")
    path = Path(store.path)
    state = json.loads(path.read_text())
    record = state["connections"][result["connection"]["id"]]
    record.pop("access")
    record.pop("collection_ids")
    path.write_text(json.dumps(state))
    assert store.authenticate(result["token"])["access"] == "manage"


def test_inconsistent_saved_connection_scope_fails_closed(tmp_path):
    store = ConnectionStore(str(tmp_path / "connections.json"))
    result = store.create("Existing")
    path = Path(store.path)
    state = json.loads(path.read_text())
    state["connections"][result["connection"]["id"]]["collection_ids"] = ["collection"]
    path.write_text(json.dumps(state))
    with pytest.raises(StateError):
        store.authenticate(result["token"])
