import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from bottle import default_app
from webtest import TestApp


TEST_STATE_DIR = tempfile.mkdtemp(prefix="youtube-dl-nas-tests-")
os.environ.update({
    "STATE_DIR": TEST_STATE_DIR,
    "MY_ID": "tester",
    "MY_PW": "secret",
    "TERMS_ACCEPTED": "Y",
    "YDLNAS_API_TOKEN": "integration-token",
})

MODULE_PATH = Path(__file__).resolve().parents[1] / "youtube-dl-server.py"
sys.path.insert(0, str(MODULE_PATH.parent))
from i18n import CATALOGS

SPEC = importlib.util.spec_from_file_location("youtube_dl_nas_server", MODULE_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


@pytest.fixture
def app():
    return TestApp(default_app())


def test_health_and_manifest_are_public(app):
    health = app.get("/health")
    assert health.json["status"] == "ok"
    assert health.json["version"] == "26.0804"

    manifest = app.get("/manifest.webmanifest")
    assert manifest.json["share_target"]["action"] == "/youtube-dl/share-target"
    assert manifest.json["share_target"]["method"] == "POST"


def test_queue_endpoints_require_login(app):
    get_error = app.get("/youtube-dl/q", status=403).json
    post_error = app.post_json(
        "/youtube-dl/q",
        {"url": "https://youtu.be/example", "resolution": "best"},
        status=403,
    ).json

    assert get_error["msg"] == "Unauthorized"
    assert get_error["code"] == "unauthorized"
    assert post_error["msg"] == "Unauthorized"
    assert post_error["code"] == "unauthorized"


def test_login_rejects_empty_credentials_when_account_is_unconfigured(app):
    with patch.object(server, "load_auth_data", return_value={"MY_ID": "", "MY_PW": "", "SECRET_KEY": "test"}):
        response = app.post("/login", {"id": "", "myPw": "", "next": "/youtube-dl"})
    assert "The ID or password is incorrect." in response.text


def test_accept_language_renders_localized_login(app):
    response = app.get("/", headers={"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"})
    assert '<html lang="pl-PL">' in response.text
    assert "Witaj ponownie" in response.text
    assert "Zaloguj się" in response.text


def test_locale_selection_persists_in_cookie(app):
    response = app.post(
        "/locale",
        {"locale": "zh-CN", "next": "/"},
        status=302,
    )
    assert response.location.endswith("/")

    login = app.get("/")
    assert '<html lang="zh-CN">' in login.text
    assert "欢迎回来" in login.text
    assert '<option value="zh-CN" selected>' in login.text


def test_selected_locale_renders_dashboard_catalog(app):
    app.post("/locale", {"locale": "ko-KR", "next": "/"}, status=302)
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    dashboard = app.get("/youtube-dl")

    assert '<html lang="ko-KR">' in dashboard.text
    assert "다운로드 대기열 및 기록 관리자" in dashboard.text
    assert "파일 및 기록" in dashboard.text
    assert 'window.YDLNAS_LOCALE = "ko-KR"' in dashboard.text


def test_accept_language_renders_localized_terms(app):
    terms = app.get("/terms", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    assert '<html lang="zh-CN">' in terms.text
    assert "使用条款" in terms.text
    assert "继续进入应用" in terms.text


def test_terms_acceptance_failure_does_not_expose_internal_error(app):
    with patch.object(server, "save_app_state", side_effect=OSError("private filesystem detail")):
        response = app.post("/accept-terms")

    assert response.json == {"success": False}


def test_invalid_locale_redirects_without_open_redirect(app):
    response = app.post(
        "/locale",
        {"locale": "invalid", "next": "https://example.com"},
        status=302,
    )
    assert response.location.endswith("/")


def test_rest_api_keeps_id_password_auth(app):
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post_json("/youtube-dl/rest", {
            "url": "https://youtu.be/example",
            "resolution": "best",
            "id": "tester",
            "pw": "secret",
        })
    assert response.json["success"] is True
    enqueue.assert_called_once_with("https://youtu.be/example", "best", "api", "", force=False)


def test_rest_api_accepts_optional_bearer_token(app):
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post_json(
            "/youtube-dl/rest",
            {"url": "https://youtu.be/example", "resolution": "audio-m4a"},
            headers={"Authorization": "Bearer integration-token"},
        )
    assert response.json["success"] is True
    enqueue.assert_called_once()


def test_rest_api_rejects_empty_or_invalid_credentials(app):
    empty_credentials = app.post_json(
        "/youtube-dl/rest",
        {"url": "https://youtu.be/example", "resolution": "best"},
        status=403,
    ).json
    invalid_credentials = app.post_json(
        "/youtube-dl/rest",
        {"url": "https://youtu.be/example", "resolution": "best", "id": "tester", "pw": "wrong"},
        status=403,
    ).json

    assert empty_credentials["code"] == "invalid_credentials"
    assert invalid_credentials["code"] == "invalid_credentials"


def test_json_errors_include_stable_localization_codes_and_parameters():
    assert server.get_error_details("URL is required") == ("url_required", {})
    assert server.get_error_details("Unsupported resolution") == ("unsupported_resolution", {})
    assert server.get_error_details("Unmapped diagnostic") == (None, {})
    assert server.get_error_details("Reference transcript exceeds 100000 characters") == (
        "reference_too_large",
        {"limit": 100000},
    )


def test_server_error_codes_have_translations_in_every_catalog():
    error_codes = set(server.ERROR_CODE_BY_MESSAGE.values()) | {"reference_too_large"}
    for locale, catalog in CATALOGS.items():
        assert {f"server.{code}" for code in error_codes} <= set(catalog), locale


def test_login_then_share_target_queues_url(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post(
            "/youtube-dl/share-target",
            {"text": "Watch https://youtu.be/shared123"},
            status=302,
        )
    assert response.location.endswith("/youtube-dl?shared=queued")
    enqueue.assert_called_once_with("https://youtu.be/shared123", "best", "web", server.ws_addr.wsClassVal)


def test_share_target_survives_login_without_putting_url_in_redirect(app):
    response = app.post(
        "/youtube-dl/share-target",
        {"url": "https://youtu.be/pending123"},
        status=302,
    )
    assert "pending123" not in response.location
    assert response.location.endswith("next=%2Fyoutube-dl%2Fshare-target%2Fcomplete")

    app.post(
        "/login",
        {"id": "tester", "myPw": "secret", "next": "/youtube-dl/share-target/complete"},
        status=302,
    )
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        completed = app.get("/youtube-dl/share-target/complete", status=302)
    assert completed.location.endswith("/youtube-dl?shared=queued")
    enqueue.assert_called_once_with("https://youtu.be/pending123", "best", "web", server.ws_addr.wsClassVal)


def test_safe_redirect_and_shared_url_helpers():
    assert server.safe_next_path("/youtube-dl?shared=1") == "/youtube-dl?shared=1"
    assert server.safe_next_path("//example.com") == "/youtube-dl"
    assert server.extract_shared_url("Watch https://youtu.be/abc?t=4.") == "https://youtu.be/abc?t=4"


def test_unresolved_auth_placeholders_are_ignored():
    with patch.object(server, "load_json_file") as load_json:
        load_json.side_effect = [
            {"MY_ID": "{{MY_ID}}", "MY_PW": "{{MY_PW}}", "PROXY": "{{PROXY}}"},
            {"SECRET_KEY": "state-secret", "TERMS_ACCEPTED": "Y"},
        ]
        with patch.dict(os.environ, {"MY_ID": "tester", "MY_PW": "secret"}, clear=False):
            data = server.load_auth_data()
    assert data["MY_ID"] == "tester"
    assert data["MY_PW"] == "secret"
    assert data["PROXY"] == ""


def test_download_command_uses_temp_path_and_final_path_marker():
    command = server.build_youtube_dl_cmd(("https://youtu.be/example", "", "best", "api"))
    assert "home:./downfolder" in command
    assert "temp:./downfolder/.incomplete" in command
    assert server.YTDLP_OUTPUT_TEMPLATE in command
    assert "%(extractor_key)s" in server.YTDLP_OUTPUT_TEMPLATE
    assert "%(id)s" in server.YTDLP_OUTPUT_TEMPLATE
    assert "after_move:__YDLNAS_FILE__:%(filepath)s" in command
    assert "--continue" in command
    assert "--exec" not in command


def test_forced_download_command_overwrites_existing_output():
    command = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example",
        "resolution": "best",
        "source": "api",
        "force": True,
    })
    assert "--force-overwrites" in command


def test_instagram_generic_titles_include_reel_id():
    first = {
        "extractor_key": "Instagram",
        "id": "DapoFfVlR7F",
        "title": "Video by technicallyhash",
    }
    second = {
        "extractor_key": "Instagram",
        "id": "Daxhbdmk5G9",
        "title": "Video by technicallyhash",
    }

    assert server.get_media_display_title(first, "") == "Video by technicallyhash [DapoFfVlR7F]"
    assert server.get_media_display_title(second, "") == "Video by technicallyhash [Daxhbdmk5G9]"
    assert server.get_media_display_title(first, "") != server.get_media_display_title(second, "")


def test_output_template_separates_same_title_media():
    shared = {
        "title": "Video_by_technicallyhash",
        "extractor_key": "Instagram",
        "ext": "mp4",
    }
    first_filename = server.YTDLP_OUTPUT_TEMPLATE % {**shared, "id": "DapoFfVlR7F"}
    second_filename = server.YTDLP_OUTPUT_TEMPLATE % {**shared, "id": "Daxhbdmk5G9"}

    assert first_filename == "Video_by_technicallyhash__Instagram_DapoFfVlR7F.mp4"
    assert second_filename == "Video_by_technicallyhash__Instagram_Daxhbdmk5G9.mp4"
    assert first_filename != second_filename


def test_non_instagram_titles_remain_unchanged():
    metadata = {
        "extractor_key": "Youtube",
        "id": "example",
        "title": "Video by Example Creator",
    }
    assert server.get_media_display_title(metadata, "") == "Video by Example Creator"


def test_queue_listing_is_json_serializable(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        server.dl_q.queue.clear()
        server.dl_q.queue.append(("https://youtu.be/example", object(), "best", "web"))
    try:
        response = app.get("/youtube-dl/q")
        assert response.json["count"] == 1
        assert "https://youtu.be/example" in response.json["size"]
        item = response.json["items"][0]
        assert item["position"] == 1
        assert item["url"] == "https://youtu.be/example"
        assert item["resolution"] == "best"
        assert item["source"] == "web"
        assert item["id"]
        assert item["restored"] is False
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)


def test_status_includes_visible_queue_items(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        server.dl_q.queue.clear()
        server.dl_q.queue.append(("https://youtu.be/queued", object(), "audio-mp3", "api"))
    try:
        response = app.get("/youtube-dl/status")
        assert response.json["queue_count"] == 1
        assert response.json["queue"][0]["url"] == "https://youtu.be/queued"
        assert response.json["queue"][0]["resolution"] == "audio-mp3"
        assert response.json["queue"][0]["source"] == "api"
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)


def test_media_url_normalization_removes_tracking_but_keeps_media_options():
    assert server.normalize_media_url(
        "https://www.instagram.com/reel/ABC123/?utm_source=share&igsh=token"
    ) == "https://www.instagram.com/reel/ABC123"
    assert server.normalize_media_url(
        "https://youtu.be/example?si=share-token&t=45"
    ) == "https://youtu.be/example"
    assert server.normalize_media_url(
        "https://www.youtube.com/watch?v=example&list=playlist"
    ) == "https://www.youtube.com/watch?list=playlist&v=example"


def test_queue_state_restores_active_before_pending(tmp_path):
    state_file = tmp_path / "queue_state.json"
    active = server.create_queue_job("https://youtu.be/active", "best", "web")
    pending = server.create_queue_job("https://youtu.be/pending", "audio-mp3", "api")
    original_active = server.active_queue_job
    original_loaded = server.queue_state_loaded
    original_restore_count = server.queue_restore_count
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    try:
        with patch.object(server, "QUEUE_STATE_FILE", str(state_file)):
            server.active_queue_job = active
            server.dl_q.put(pending)
            server.persist_queue_state()

            saved = json.loads(state_file.read_text(encoding="utf-8"))
            assert saved["active"]["id"] == active["id"]
            assert saved["pending"][0]["id"] == pending["id"]

            with server.dl_q.mutex:
                server.dl_q.queue.clear()
                server.dl_q.unfinished_tasks = 0
            server.active_queue_job = None
            server.queue_state_loaded = False
            server.queue_restore_count = 0

            assert server.load_persisted_queue() == 2
            restored = server.pending_queue_jobs()
            assert [job["id"] for job in restored] == [active["id"], pending["id"]]
            assert all(job["restored"] for job in restored)
            assert all(job["attempts"] == 1 for job in restored)
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
            server.dl_q.unfinished_tasks = original_unfinished
        server.active_queue_job = original_active
        server.queue_state_loaded = original_loaded
        server.queue_restore_count = original_restore_count


def test_duplicate_queue_guard_ignores_share_tracking_parameters(tmp_path):
    original_active = server.active_queue_job
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    try:
        with patch.object(server, "QUEUE_STATE_FILE", str(tmp_path / "queue.json")), \
             patch.object(server, "find_existing_download", return_value=None), \
             patch.object(server, "start_download_thread_if_needed"):
            first = server.enqueue_download(
                "https://www.instagram.com/reel/ABC123/?utm_source=share",
                "best",
                "web",
            )
            duplicate = server.enqueue_download(
                "https://www.instagram.com/reel/ABC123/?igsh=another-token",
                "best",
                "api",
            )
            other_profile = server.enqueue_download(
                "https://www.instagram.com/reel/ABC123/",
                "audio-mp3",
                "web",
            )

        assert first["queued"] is True
        assert duplicate["duplicate"] is True
        assert duplicate["duplicate_type"] == "queue"
        assert other_profile["queued"] is True
        assert len(server.pending_queue_jobs()) == 2
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
            server.dl_q.unfinished_tasks = original_unfinished
        server.active_queue_job = original_active


def test_remove_queued_download_endpoint(app, tmp_path):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    job = server.create_queue_job("https://youtu.be/remove-me", "best", "web")
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    try:
        with patch.object(server, "QUEUE_STATE_FILE", str(tmp_path / "queue.json")):
            server.dl_q.put(job)
            response = app.post(f"/youtube-dl/q/{job['id']}/remove")
        assert response.json["success"] is True
        assert response.json["removed"]["id"] == job["id"]
        assert server.pending_queue_jobs() == []
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
            server.dl_q.unfinished_tasks = original_unfinished


def test_existing_file_can_be_matched_by_extractor_and_media_id(tmp_path):
    filename = "Video_by_creator__Instagram_ABC123.mp4"
    (tmp_path / filename).write_bytes(b"media")
    history = [{
        "uuid": "existing",
        "url": "https://www.instagram.com/reel/old-url",
        "resolution": "best",
        "title": "Existing reel",
        "filename": filename,
        "status": "completed",
    }]

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), \
         patch.object(server.download_manager, "download_history", history):
        existing = server.find_existing_download(
            "https://www.instagram.com/reel/new-url",
            "best",
            media_id="ABC123",
            extractor="Instagram",
        )

    assert existing["uuid"] == "existing"
    assert existing["filename"] == filename


def test_worker_shutdown_preserves_active_and_pending_queue_state(tmp_path):
    active = server.create_queue_job("https://youtu.be/active-shutdown", "best", "web")
    pending = server.create_queue_job("https://youtu.be/pending-shutdown", "audio-mp3", "api")
    original_active = server.active_queue_job
    original_shutdown = server.shutdown_event.is_set()
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    def stop_during_download(_job):
        server.shutdown_event.set()

    try:
        server.shutdown_event.clear()
        server.dl_q.put(active)
        server.dl_q.put(pending)
        with patch.object(server, "QUEUE_STATE_FILE", str(tmp_path / "queue.json")), \
             patch.object(server, "download", side_effect=stop_during_download):
            server.dl_worker()
            saved = json.loads((tmp_path / "queue.json").read_text(encoding="utf-8"))

        assert saved["active"]["id"] == active["id"]
        assert [job["id"] for job in saved["pending"]] == [pending["id"]]
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
            server.dl_q.unfinished_tasks = original_unfinished
        server.active_queue_job = original_active
        if original_shutdown:
            server.shutdown_event.set()
        else:
            server.shutdown_event.clear()


def test_history_normalization_preserves_media_preview_metadata():
    item = server.normalize_history_item({
        "uuid": "media-item",
        "title": "Example",
        "thumbnail": "https://i.ytimg.com/vi/example/hqdefault.jpg",
        "duration_seconds": 125,
    })
    assert item["thumbnail"].endswith("hqdefault.jpg")
    assert item["duration_seconds"] == 125


def test_preview_requires_login_and_serves_media_inline(app, tmp_path):
    media_file = tmp_path / "preview.mp4"
    media_file.write_bytes(b"preview-data")
    history_item = {
        "uuid": "preview-item",
        "filename": media_file.name,
        "filepath": str(media_file),
        "status": "completed",
        "resolution": "best",
    }

    app.get("/static/preview/preview-item", status=403)
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), \
         patch.object(server.download_manager, "load_history"), \
         patch.object(server.download_manager, "get_combined_history_item", return_value=history_item):
        response = app.get("/static/preview/preview-item")

    assert response.body == b"preview-data"
    assert response.content_type == "video/mp4"
    assert "attachment" not in response.headers.get("Content-Disposition", "").lower()


def test_extract_subtitle_text_supports_srt_vtt_and_ass():
    srt = """1
00:00:00,000 --> 00:00:02,000
<i>안녕하세요</i>

2
00:00:02,100 --> 00:00:04,000
Azure AI 테스트입니다.
"""
    vtt = """WEBVTT

cue-1
00:00:00.000 --> 00:00:02.000
Hello &amp; welcome
"""
    ass = """[Events]
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{\\i1}첫 문장{\\i0}\\N둘째 문장
"""

    assert server.extract_subtitle_text(srt, ".srt") == "안녕하세요 Azure AI 테스트입니다."
    assert server.extract_subtitle_text(vtt, ".vtt") == "Hello & welcome"
    assert server.extract_subtitle_text(ass, ".ass") == "첫 문장 둘째 문장"


def test_analyze_subtitle_text_uses_nlptutti_metrics_and_keywords():
    result = server.analyze_subtitle_text(
        "안녕하세요 Azure AI 테스트입니다",
        "안녕하세요 Azure AI 테스트입니다",
        ["Azure AI"],
    )

    assert result["cer"]["cer"] == 0
    assert result["wer"]["wer"] == 0
    assert result["crr"]["crr"] == 1
    assert result["keywords"][0]["preservation_rate"] == 1
    assert result["nlptutti_version"] != "unavailable"


def test_subtitle_qa_requires_login(app):
    response = app.post_json(
        "/youtube-dl/subtitle-qa/subtitle-item",
        {"reference": "reference text"},
        status=403,
    )
    assert response.json["msg"] == "Unauthorized"


def test_subtitle_qa_analyzes_stored_subtitle(app, tmp_path):
    subtitle_file = tmp_path / "sample.ko.srt"
    subtitle_file.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n안녕하세요 Azure AI 테스트입니다\n",
        encoding="utf-8",
    )
    history_item = {
        "uuid": "subtitle-item",
        "title": "Sample subtitle",
        "filename": subtitle_file.name,
        "filepath": str(subtitle_file),
        "status": "completed",
        "resolution": "srt|ko",
    }

    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), \
         patch.object(server.download_manager, "load_history"), \
         patch.object(server.download_manager, "get_combined_history_item", return_value=history_item):
        response = app.post_json(
            "/youtube-dl/subtitle-qa/subtitle-item",
            {
                "reference": "안녕하세요 Azure AI 테스트입니다",
                "keywords": "Azure AI, 누락 키워드",
            },
        )

    assert response.json["success"] is True
    assert response.json["result"]["cer"]["cer"] == 0
    assert response.json["result"]["keywords"][0]["preservation_rate"] == 1
    assert response.json["result"]["keywords"][1]["preservation_rate"] is None


def test_subtitle_qa_rejects_non_subtitle_files(app, tmp_path):
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"video")
    history_item = {
        "uuid": "video-item",
        "filename": video_file.name,
        "status": "completed",
        "resolution": "best",
    }

    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), \
         patch.object(server.download_manager, "load_history"), \
         patch.object(server.download_manager, "get_combined_history_item", return_value=history_item):
        response = app.post_json(
            "/youtube-dl/subtitle-qa/video-item",
            {"reference": "reference text"},
            status=400,
        )

    assert "SRT, VTT, ASS, and SSA" in response.json["msg"]
