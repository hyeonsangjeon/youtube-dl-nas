import json
from unittest.mock import patch

import pytest
from yt_dlp import YoutubeDL

from test_collections import (
    AUTH, BASE, approve, client, finish_job, isolated_backend, login, make_plan,
    restart_backend, server, stable_public_source_network,
)


@pytest.mark.parametrize("style,prefix", [
    ("default", "Lesson"), ("channel-title", "Studio - Lesson"),
    ("date-title", "2026-10-12 - Lesson"),
])
@pytest.mark.parametrize("resolution", ["best", "audio-mp3", "vtt|ko"])
def test_filename_styles_keep_media_identity_and_extension(style, prefix, resolution):
    job = server.normalize_queue_job({
        "url": "https://example.com/video", "resolution": resolution,
        "created_at": "2026-10-12T02:51:00", "filename_style": style,
    })
    cmd = server.build_youtube_dl_cmd(job)
    template = cmd[cmd.index("-o") + 1]
    with YoutubeDL({"outtmpl": template, "quiet": True}) as ydl:
        filename = ydl.prepare_filename({
            "title": "Lesson", "uploader": "Studio", "extractor_key": "Test",
            "id": "unique123", "ext": "mp4",
        })
    assert filename == prefix + "__Test_unique123.mp4"
    assert "--skip-download" in cmd if resolution.startswith("vtt") else "--skip-download" not in cmd


def test_custom_title_is_literal_not_an_output_template():
    job = server.create_queue_job("https://youtu.be/video?t=30", "best", "web",
                                  filename_title="My %(id)s 100%", section_mode="from_timestamp")
    with YoutubeDL({"outtmpl": server.download_output_template(job), "quiet": True}) as ydl:
        filename = ydl.prepare_filename({"title": "Original", "extractor_key": "Test", "id": "123", "ext": "mp4"})
    assert filename == "My %(id)s 100%__from_30s__Test_123.mp4"


def test_channel_naming_bounds_metadata_without_trimming_media_identity():
    job = server.create_queue_job("https://example.com/video", "best", "web", filename_style="channel-title")
    with YoutubeDL({"outtmpl": server.download_output_template(job), "quiet": True}) as ydl:
        filename = ydl.prepare_filename({"title": "한" * 200, "uploader": "界" * 100,
                                         "extractor_key": "Instagram", "id": "Da2_llXtwnG", "ext": "mp4"})
    assert len(filename.encode("utf-8")) < 255
    assert filename.endswith("__Instagram_Da2_llXtwnG.mp4")


@pytest.mark.parametrize("options", [
    {"filename_style": "../../outside"}, {"filename_style": None},
    {"filename_title": "../escape"}, {"filename_title": ".."},
    {"filename_title": "C:\\escape"}, {"filename_title": "line\nbreak"},
    {"filename_title": ["bad"]}, {"filename_title": "x" * 81},
    {"filename_title": "한" * 80}, {"filename_title": "trail."},
])
@pytest.mark.parametrize("endpoint", ["/youtube-dl/q", "/youtube-dl/rest", BASE + "/downloads"])
def test_naming_rejects_unsafe_options_before_queueing(client, options, endpoint):
    login(client)
    result = client.post_json(endpoint, {
        "url": "https://example.com/video", "resolution": "best", **options,
    }, headers=AUTH, status=400).json
    assert result.get("code") in {"unsupported_filename_style", "invalid_filename_title"}
    assert server.pending_queue_jobs() == []


@pytest.mark.parametrize("endpoint", ["/youtube-dl/q", "/youtube-dl/rest", BASE + "/downloads"])
def test_naming_survives_queue_restart_completion_and_retry(client, isolated_backend, monkeypatch, endpoint):
    login(client)
    result = client.post_json(endpoint, {
        "url": "https://example.com/video", "resolution": "best",
        "filename_style": "date-title", "filename_title": "My lesson",
    }, headers=AUTH).json
    assert result["queued"]
    before = server.pending_queue_jobs()[0]
    restart_backend(monkeypatch)
    after = server.pending_queue_jobs()[0]
    for key in ("filename_style", "filename_title", "filename_date"):
        assert after[key] == before[key]
    output = server.build_completed_history_item(after, {
        "filepath": str(isolated_backend[0] / "saved__Test_1.mp4"), "id": "1", "extractor_key": "Test",
    }, {})
    assert output["filename_title"] == "My lesson"
    server.download_manager.download_history = [{**output, "status": "failed", "failure_code": "format_unavailable"}]
    server.download_manager.save_history()
    with server.dl_q.mutex:
        server.dl_q.queue.clear()
    server.persist_queue_state()
    result = client.post_json("/youtube-dl/history/retry/" + output["uuid"], {"resolution": "720p"}).json
    assert result["queued"]
    retried = server.pending_queue_jobs()[0]
    assert retried["resolution"] == "720p"
    assert retried["filename_title"] == "My lesson"
    assert retried["filename_date"] == before["filename_date"]


def test_new_name_does_not_duplicate_or_rename_existing_media(client, isolated_backend):
    media = isolated_backend[0] / "original__Youtube_first.mp4"
    media.write_bytes(b"kept")
    server.download_manager.download_history = [{
        "uuid": "saved", "filename": media.name, "url": "https://youtu.be/first",
        "resolution": "best", "status": "completed", "media_id": "first", "extractor": "Youtube",
    }]
    result = server.enqueue_download("https://youtu.be/first", "best", "web", filename_title="New name")
    assert result["duplicate"] and not result["queued"]
    assert media.read_bytes() == b"kept"
    assert list(isolated_backend[0].iterdir()) == [media]


def test_diagnostics_require_login_and_exclude_user_content(client):
    client.get("/youtube-dl/history/diagnostics/failed", status=403)
    server.download_manager.download_history = [{
        "uuid": "failed", "status": "failed", "failure_code": "auth_required", "resolution": "720p",
        "url": "https://secret.example/path?token=hidden", "title": "private title", "filename": "private.mp4",
        "filepath": "/secret/location", "cookie": "secret-session", "stderr": "secret-token",
    }]
    login(client)
    diagnostics = client.get("/youtube-dl/history/diagnostics/failed").json["diagnostics"]
    assert set(diagnostics) == {"app_version", "yt_dlp_version", "status", "failure_code", "profile", "storage_state"}
    assert diagnostics["failure_code"] == "auth_required"
    assert not any(value in json.dumps(diagnostics) for value in ("secret", "private", "hidden"))
    client.get("/youtube-dl/history/diagnostics/missing", status=404)
    server.download_manager.download_history[0].update(status=[], failure_code={}, resolution=[])
    diagnostics = client.get("/youtube-dl/history/diagnostics/failed").json["diagnostics"]
    assert diagnostics["status"] == diagnostics["failure_code"] == diagnostics["profile"] == "unknown"


def test_retry_profile_rejects_invalid_options_and_preserves_collection(client, isolated_backend):
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    finish_job(isolated_backend[0], job)
    server.dl_q.get_nowait()
    server.dl_q.task_done()
    server.persist_queue_state()
    item = server.download_manager.download_history[0]
    login(client)
    client.post_json("/youtube-dl/history/retry/" + item["uuid"], {"resolution": "--exec bad"}, status=400)
    client.post_json("/youtube-dl/history/retry/" + item["uuid"], {"filepath": "/outside"}, status=400)
    result = client.post_json("/youtube-dl/history/retry/" + item["uuid"], {"resolution": "720p"}).json
    assert result["queued"]
    retry = server.pending_queue_jobs()[0]
    assert retry["resolution"] == "720p"
    assert retry["collection_id"] == receipt["collection"]["id"]
    assert retry["target_relative_directory"] == job["target_relative_directory"]
    assert retry["date_policy"] == job["date_policy"]


@pytest.mark.parametrize("completed", [True, False])
def test_tightening_source_policy_loads_collections_but_blocks_transfers(client, isolated_backend, monkeypatch, completed):
    monkeypatch.setattr(server, "YDLNAS_ALLOW_PRIVATE_SOURCES", True)
    receipt = approve(client, make_plan(client, candidates=[{"url": "http://127.0.0.1/video"}]))
    job = server.pending_queue_jobs()[0]
    if completed:
        finish_job(isolated_backend[0], job)
    monkeypatch.setattr(server, "YDLNAS_ALLOW_PRIVATE_SOURCES", False)
    restart_backend(monkeypatch)
    collection = server.collections_service.get_collection(receipt["collection"]["id"])
    assert len(collection["items"]) == 1
    if completed:
        assert collection["items"][0]["file_exists"]
        login(client)
        client.post("/youtube-dl/history/retry/" + collection["items"][0]["uuid"], status=400)
    else:
        assert server.pending_queue_jobs()[0]["id"] == job["id"]
        with patch.object(server.subprocess, "Popen") as process:
            server.download(job)
        process.assert_not_called()
        assert server.download_manager.download_history[-1]["failure_code"] == "source_blocked"
    with pytest.raises(ValueError):
        server.enqueue_download("http://127.0.0.1/new", "best", "web")
    assert server.normalize_queue_job({"url": "file:///etc/passwd", "resolution": "best"}) is None
