import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    assert health.json["version"] == "26.0806"
    assert health.json["storage"]["state"] in {"ok", "warning", "critical", "unavailable"}

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
    enqueue.assert_called_once_with(
        "https://youtu.be/example",
        "best",
        "api",
        "",
        force=False,
        playlist_mode="single",
        write_thumbnail=False,
        section_mode="full",
    )


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


def test_rest_api_reports_critical_storage_with_http_507(app):
    blocked = {
        "queued": False,
        "duplicate": False,
        "blocked": True,
        "code": "storage_critical",
        "queue_count": 0,
        "storage": {
            "state": "critical",
            "free_bytes": 512,
            "critical_bytes": 1024,
        },
    }
    with patch.object(server, "enqueue_download", return_value=blocked):
        response = app.post_json(
            "/youtube-dl/rest",
            {
                "url": "https://youtu.be/example",
                "resolution": "best",
                "id": "tester",
                "pw": "secret",
            },
            status=507,
        )

    assert response.json["success"] is False
    assert response.json["blocked"] is True
    assert response.json["code"] == "storage_critical"


def test_rest_api_preserves_advanced_resolution_values(app):
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post_json(
            "/youtube-dl/rest",
            {
                "url": "https://youtu.be/example",
                "resolution": "2160p",
                "id": "tester",
                "pw": "secret",
            },
        )

    assert response.json["success"] is True
    assert response.json["profile"] == "2160p"
    assert enqueue.call_args.args[1] == "2160p"


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


def test_playlist_and_channel_requests_require_explicit_bulk_scope(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    response = app.post_json(
        "/youtube-dl/q",
        {
            "url": "https://www.youtube.com/playlist?list=PL123",
            "resolution": "best",
        },
        status=400,
    )
    assert response.json["code"] == "playlist_scope_required"

    single_response = app.post_json(
        "/youtube-dl/q",
        {
            "url": "https://www.youtube.com/playlist?list=PL123",
            "resolution": "best",
            "playlist_mode": "single",
        },
        status=400,
    )
    assert single_response.json["code"] == "playlist_scope_required"


def test_video_inside_playlist_defaults_to_current_video(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post_json(
            "/youtube-dl/q",
            {
                "url": "https://www.youtube.com/watch?v=abc&list=PL123",
                "resolution": "best",
            },
        )

    assert response.json["queued"] is True
    enqueue.assert_called_once_with(
        "https://www.youtube.com/watch?v=abc&list=PL123",
        "best",
        "web",
        server.ws_addr.wsClassVal,
        force=False,
        playlist_mode="single",
        write_thumbnail=False,
        section_mode="full",
    )


def test_explicit_playlist_options_reach_persistent_queue_contract(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post_json(
            "/youtube-dl/q",
            {
                "url": "https://www.youtube.com/playlist?list=PL123",
                "resolution": "1080p",
                "playlist_mode": "first10",
                "write_thumbnail": True,
            },
        )

    assert response.json["queued"] is True
    enqueue.assert_called_once_with(
        "https://www.youtube.com/playlist?list=PL123",
        "1080p",
        "web",
        server.ws_addr.wsClassVal,
        force=False,
        playlist_mode="first10",
        write_thumbnail=True,
        section_mode="full",
    )


def test_smart_share_context_extracts_url_profile_playlist_and_timestamp(app):
    response = app.post_json(
        "/youtube-dl/share/context",
        {
            "text": "Watch https://www.youtube.com/watch?v=abc&list=PL123&t=1m30s",
            "profile": "MP3",
            "id": "tester",
            "pw": "secret",
        },
    )

    assert response.json["code"] == "share_context"
    assert response.json["url"].endswith("v=abc&list=PL123&t=1m30s")
    assert response.json["profile"] == "audio-mp3"
    assert response.json["playlist_kind"] == ""
    assert response.json["timestamp_seconds"] == 90
    assert response.json["timestamp_label"] == "1:30"
    assert response.json["timestamp_options"] == ["full", "from_timestamp"]


def test_smart_share_context_marks_pure_playlists_for_scope_prompt(app):
    response = app.post_json(
        "/youtube-dl/share/context",
        {
            "url": "https://www.youtube.com/playlist?list=PL123",
            "resolution": "ask",
            "id": "tester",
            "pw": "secret",
        },
    )

    assert response.json["profile_required"] is True
    assert response.json["playlist_kind"] == "playlist"
    assert response.json["playlist_options"] == ["first10", "all"]


def test_smart_share_context_can_return_soft_missing_url_for_shortcut_fallback(app):
    response = app.post_json(
        "/youtube-dl/share/context",
        {
            "text": "A share payload without a link",
            "profile": "best",
            "soft_errors": True,
            "id": "tester",
            "pw": "secret",
        },
    )

    assert response.json["success"] is False
    assert response.json["code"] == "url_required"
    assert response.json["url"] == ""


def test_rest_smart_share_receipt_and_timestamp_options_reach_queue(app):
    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {
            "queued": True,
            "duplicate": False,
            "job": {"position": 2},
            "queue_count": 2,
        }
        response = app.post_json(
            "/youtube-dl/rest",
            {
                "url": "https://youtu.be/example?t=75",
                "resolution": "mp3",
                "section_mode": "from_timestamp",
                "client": "ios-shortcut",
                "client_version": "2.0",
                "id": "tester",
                "pw": "secret",
            },
        )

    assert response.json["code"] == "queued"
    assert response.json["profile"] == "audio-mp3"
    assert response.json["queue_position"] == 2
    assert response.json["queue_count"] == 2
    assert response.json["client"] == "ios-shortcut"
    enqueue.assert_called_once_with(
        "https://youtu.be/example?t=75",
        "audio-mp3",
        "api",
        "",
        force=False,
        playlist_mode="single",
        write_thumbnail=False,
        section_mode="from_timestamp",
    )


def test_timestamp_mode_requires_a_timestamp(app):
    response = app.post_json(
        "/youtube-dl/rest",
        {
            "url": "https://youtu.be/example",
            "resolution": "best",
            "section_mode": "from_timestamp",
            "id": "tester",
            "pw": "secret",
        },
        status=400,
    )

    assert response.json["code"] == "timestamp_not_found"


def test_queue_receipts_distinguish_waiting_and_downloaded_duplicates():
    queued_duplicate = server.build_queue_receipt(
        {
            "duplicate": True,
            "duplicate_type": "queue",
            "job": {"position": 3},
            "queue_count": 4,
        },
        "720p",
        client="ios-shortcut",
    )
    downloaded_duplicate = server.build_queue_receipt(
        {
            "duplicate": True,
            "duplicate_type": "history",
            "existing": {"title": "Saved item"},
            "queue_count": 0,
        },
        "720p",
    )

    assert queued_duplicate["code"] == "duplicate_queue"
    assert queued_duplicate["queue_position"] == 3
    assert "position 3" in queued_duplicate["msg"]
    assert downloaded_duplicate["code"] == "duplicate_history"
    assert downloaded_duplicate["existing"]["title"] == "Saved item"


def test_storage_receipt_is_stable_and_actionable():
    receipt = server.build_queue_receipt(
        {
            "blocked": True,
            "code": "storage_critical",
            "queue_count": 2,
            "storage": {
                "state": "critical",
                "free_bytes": 512,
                "critical_bytes": 1024,
            },
        },
        "best",
        client="android-shortcut",
    )

    assert receipt["success"] is False
    assert receipt["queued"] is False
    assert receipt["code"] == "storage_critical"
    assert receipt["queue_count"] == 2
    assert receipt["params"] == {"free_bytes": 512, "critical_bytes": 1024}


@pytest.mark.parametrize(
    ("free_gb", "expected_state", "expected_blocking"),
    [
        (20, "ok", False),
        (5, "warning", False),
        (1, "critical", True),
    ],
)
def test_storage_status_uses_warning_and_critical_thresholds(free_gb, expected_state, expected_blocking):
    class Usage:
        total = 100 * (1024 ** 3)
        free = free_gb * (1024 ** 3)
        used = total - free

    with patch.object(server.shutil, "disk_usage", return_value=Usage()), \
         patch.object(server, "STORAGE_WARNING_GB", 10), \
         patch.object(server, "STORAGE_CRITICAL_GB", 2):
        storage = server.get_storage_status()

    assert storage["state"] == expected_state
    assert storage["blocking"] is expected_blocking
    assert storage["free_percent"] == float(free_gb)


def test_storage_status_fails_open_when_capacity_is_unavailable():
    with patch.object(server.shutil, "disk_usage", side_effect=OSError("not mounted")):
        storage = server.get_storage_status()

    assert storage["available"] is False
    assert storage["state"] == "unavailable"
    assert storage["blocking"] is False
    assert storage["free_bytes"] is None


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


def test_mobile_share_uses_signed_device_profile(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    preference = app.post_json("/youtube-dl/preferences", {"share_profile": "720p"})
    assert preference.json["share_profile"] == "720p"

    with patch.object(server, "enqueue_download") as enqueue:
        enqueue.return_value = {"queued": True, "duplicate": False, "job": {}}
        response = app.post(
            "/youtube-dl/share-target",
            {"text": "Watch https://youtu.be/shared-profile"},
            status=302,
        )

    assert response.location.endswith("/youtube-dl?shared=queued")
    enqueue.assert_called_once_with(
        "https://youtu.be/shared-profile",
        "720p",
        "web",
        server.ws_addr.wsClassVal,
    )


def test_mobile_share_ask_mode_prefills_after_authentication(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    app.post_json("/youtube-dl/preferences", {"share_profile": "ask"})

    response = app.post(
        "/youtube-dl/share-target",
        {"url": "https://youtu.be/review-me"},
        status=302,
    )
    assert "review-me" not in response.location
    assert response.location.endswith("/youtube-dl?shared=review")

    dashboard = app.get(response.location)
    assert 'window.YDLNAS_SHARED_URL = "https://youtu.be/review-me"' in dashboard.text
    assert "Ask every time" in dashboard.text


def test_preferences_reject_unsupported_share_profile(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    response = app.post_json(
        "/youtube-dl/preferences",
        {"share_profile": "unbounded"},
        status=400,
    )
    assert response.json["code"] == "unsupported_share_profile"


def test_safe_redirect_and_shared_url_helpers():
    assert server.safe_next_path("/youtube-dl?shared=1") == "/youtube-dl?shared=1"
    assert server.safe_next_path("//example.com") == "/youtube-dl"
    assert server.extract_shared_url("Watch https://youtu.be/abc?t=4.") == "https://youtu.be/abc?t=4"
    assert server.classify_playlist_url("https://www.youtube.com/watch?v=abc&list=PL123") == "video_playlist"
    assert server.classify_playlist_url("https://www.youtube.com/playlist?list=PL123") == "playlist"
    assert server.classify_playlist_url("https://www.youtube.com/@creator/videos") == "channel"
    assert server.extract_shared_timestamp("https://youtu.be/abc?t=1h2m3s") == 3723
    assert server.extract_shared_timestamp("https://youtu.be/abc#t=01:30") == 90
    assert server.extract_shared_timestamp("https://example.com/video?t=90") == 0


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
    marker = next(value for value in command if value.startswith("after_move:__YDLNAS_ITEM__:"))
    assert '"filepath":%(filepath|"")j' in marker
    assert "%()j" not in marker
    assert "--continue" in command
    assert "--no-playlist" in command
    assert "--exec" not in command


def test_download_profiles_have_bounded_format_fallbacks():
    best = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example",
        "resolution": "best",
        "source": "web",
    })
    capped = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example",
        "resolution": "720p",
        "source": "web",
    })
    m4a = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example",
        "resolution": "audio-m4a",
        "source": "web",
    })

    assert "/bestvideo+bestaudio/best" in best[best.index("-f") + 1]
    assert "best[height<=720]" in capped[capped.index("-f") + 1]
    assert capped[capped.index("--merge-output-format") + 1] == "mp4"
    assert "bestaudio/best" in m4a[m4a.index("-f") + 1]
    assert m4a[m4a.index("--audio-format") + 1] == "m4a"


def test_metadata_process_is_attached_to_active_job_for_cancellation():
    class FakeProcess:
        returncode = 0

        def communicate(self, timeout):
            assert timeout == 30
            return ('{"title": "Metadata title"}', None)

    process = FakeProcess()
    with patch.object(server.subprocess, "Popen", return_value=process), \
         patch.object(server.download_manager, "attach_process") as attach, \
         patch.object(server.download_manager, "detach_process") as detach:
        metadata = server.fetch_media_metadata("https://example.com/media", "metadata-job")

    assert metadata["title"] == "Metadata title"
    attach.assert_called_once_with("metadata-job", process)
    detach.assert_called_once_with("metadata-job", process)


def test_metadata_timeout_terminates_and_detaches_process():
    class FakeProcess:
        returncode = None
        calls = 0

        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise server.subprocess.TimeoutExpired(["yt-dlp", "private-value"], timeout)
            assert timeout == 6
            return ("", None)

    process = FakeProcess()
    with patch.object(server.subprocess, "Popen", return_value=process), \
         patch.object(server.download_manager, "attach_process"), \
         patch.object(server.download_manager, "detach_process") as detach, \
         patch.object(server, "terminate_process_group") as terminate:
        with pytest.raises(server.subprocess.TimeoutExpired):
            server.fetch_media_metadata("https://example.com/slow", "metadata-job")

    terminate.assert_called_once_with(process)
    detach.assert_called_once_with("metadata-job", process)


def test_failure_classification_and_diagnostics_are_safe(tmp_path):
    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)):
        diagnostic = server.sanitize_diagnostic_text(
            f"ERROR: https://private.example/watch?token=secret failed in {tmp_path}/clip.part password=hunter2"
        )

    assert "private.example" not in diagnostic
    assert str(tmp_path) not in diagnostic
    assert "hunter2" not in diagnostic
    assert server.classify_download_failure(["ERROR: HTTP Error 429: Too Many Requests"]) == "rate_limited"
    assert server.classify_download_failure(["ERROR: No space left on device"]) == "storage_full"
    assert server.classify_download_failure(["ERROR: Requested format is not available"]) == "format_unavailable"
    assert server.classify_download_failure(["unmapped failure"]) == "unknown"

    timeout = server.subprocess.TimeoutExpired(
        ["yt-dlp", "--password", "private-password", "https://private.example/media"],
        30,
    )
    timeout_diagnostic = server.sanitize_diagnostic_text(timeout)
    assert timeout_diagnostic == "process timed out"
    assert "private-password" not in timeout_diagnostic
    assert "private.example" not in timeout_diagnostic


def test_forced_download_command_overwrites_existing_output():
    command = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example",
        "resolution": "best",
        "source": "api",
        "force": True,
    })
    assert "--force-overwrites" in command


def test_playlist_and_thumbnail_options_map_to_bounded_ytdlp_flags():
    first_ten = server.build_youtube_dl_cmd({
        "url": "https://www.youtube.com/playlist?list=PL123",
        "resolution": "best",
        "source": "web",
        "playlist_mode": "first10",
        "write_thumbnail": True,
    })
    assert "--yes-playlist" in first_ten
    assert first_ten[first_ten.index("--playlist-end") + 1] == "10"
    assert "--write-thumbnail" in first_ten
    assert first_ten[first_ten.index("--convert-thumbnails") + 1] == "jpg"

    all_items = server.build_youtube_dl_cmd({
        "url": "https://www.youtube.com/playlist?list=PL123",
        "resolution": "audio-mp3",
        "source": "web",
        "playlist_mode": "all",
    })
    assert "--yes-playlist" in all_items
    assert "--playlist-end" not in all_items
    assert "--no-playlist" not in all_items


def test_timestamp_section_maps_to_bounded_ytdlp_flags():
    command = server.build_youtube_dl_cmd({
        "url": "https://youtu.be/example?t=90",
        "resolution": "best",
        "source": "api",
        "section_mode": "from_timestamp",
    })

    assert command[command.index("--download-sections") + 1] == "*90-inf"
    assert "--force-keyframes-at-cuts" in command
    assert command[command.index("-o") + 1] == (
        "%(title)s__from_90s__%(extractor_key)s_%(id)s.%(ext)s"
    )


def test_queue_job_normalization_preserves_download_options():
    job = server.create_queue_job(
        "https://www.youtube.com/playlist?list=PL123",
        "720p",
        "web",
        playlist_mode="first10",
        write_thumbnail=True,
        section_mode="full",
    )
    restored = server.normalize_queue_job(job, restored=True)
    public = server.public_queue_job(restored)

    assert restored["playlist_mode"] == "first10"
    assert restored["write_thumbnail"] is True
    assert restored["section_mode"] == "full"
    assert restored["section_start"] == 0
    assert restored["restored"] is True
    assert public["playlist_mode"] == "first10"
    assert public["write_thumbnail"] is True
    assert public["section_mode"] == "full"


def test_completed_output_json_supports_one_history_item_per_playlist_file(tmp_path):
    first = tmp_path / "first__Youtube_FIRST.mp4"
    second = tmp_path / "second__Youtube_SECOND.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    job = server.create_queue_job(
        "https://www.youtube.com/playlist?list=PL123",
        "best",
        "web",
        playlist_mode="first10",
    )
    first_output = server.parse_completed_output_line(
        f'log {server.YTDLP_ITEM_PREFIX}'
        + json.dumps({
            "filepath": str(first),
            "title": "First",
            "uploader": "Creator",
            "id": "FIRST",
            "extractor_key": "Youtube",
            "webpage_url": "https://youtu.be/FIRST",
        })
    )
    second_output = server.parse_completed_output_line(
        server.YTDLP_ITEM_PREFIX
        + json.dumps({
            "filepath": str(second),
            "title": "Second",
            "uploader": "Creator",
            "id": "SECOND",
            "extractor_key": "Youtube",
            "webpage_url": "https://youtu.be/SECOND",
        })
    )

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)):
        items = [
            server.build_completed_history_item(job, output, {}, item_uuid=f"item-{index}")
            for index, output in enumerate((first_output, second_output), start=1)
        ]

    assert [item["filename"] for item in items] == [first.name, second.name]
    assert [item["media_id"] for item in items] == ["FIRST", "SECOND"]
    assert [item["url"] for item in items] == ["https://youtu.be/FIRST", "https://youtu.be/SECOND"]


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


def test_critical_storage_blocks_new_queue_items_without_starting_worker(tmp_path):
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    try:
        with patch.object(server, "QUEUE_STATE_FILE", str(tmp_path / "queue.json")), \
             patch.object(server, "find_existing_download", return_value=None), \
             patch.object(server, "get_storage_status", return_value={
                 "available": True,
                 "state": "critical",
                 "blocking": True,
                 "free_bytes": 1024,
                 "critical_bytes": 2048,
             }), \
             patch.object(server, "start_download_thread_if_needed") as start_worker:
            result = server.enqueue_download("https://youtu.be/no-space", "best", "web")

        assert result["blocked"] is True
        assert result["code"] == "storage_critical"
        assert server.pending_queue_jobs() == []
        start_worker.assert_not_called()
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
            server.dl_q.unfinished_tasks = original_unfinished


def test_active_download_cancel_targets_the_attached_process():
    class FakeProcess:
        def poll(self):
            return None

    manager = server.GlobalDownloadManager()
    process = FakeProcess()
    manager.set_current_download({"job_id": "active-job", "status": "downloading"})
    manager.attach_process("active-job", process)

    with patch.object(server, "terminate_process_group") as terminate:
        result = manager.request_active_cancel()
        repeated = manager.request_active_cancel()

    assert result == {"job_id": "active-job", "already_requested": False}
    assert repeated == {"job_id": "active-job", "already_requested": True}
    assert manager.current_download["status"] == "canceling"
    assert manager.cancellation_requested("active-job") is True
    terminate.assert_called_once_with(process)
    assert manager.consume_cancellation("active-job") is True
    assert manager.cancellation_requested("active-job") is False


def test_process_group_cancel_escalates_after_grace_period():
    class FakeProcess:
        pid = 123

        def poll(self):
            return None

    process = FakeProcess()
    with patch.object(server.os, "name", "posix"), \
         patch.object(server.os, "getpgid", return_value=456), \
         patch.object(server.os, "killpg") as killpg, \
         patch.object(server.time, "sleep"), \
         patch.object(server, "Thread") as thread:
        server.terminate_process_group(process)
        watchdog = thread.call_args.kwargs["target"]
        watchdog()

    assert [entry.args for entry in killpg.call_args_list] == [
        (456, server.signal.SIGTERM),
        (456, server.signal.SIGKILL),
    ]
    thread.return_value.start.assert_called_once()


def test_download_canceled_during_metadata_does_not_start_process():
    manager = MagicMock()
    manager.current_download = {}
    manager.consume_cancellation.return_value = True
    job = server.create_queue_job("https://example.com/cancel-during-metadata", "best", "web")

    with patch.object(server, "download_manager", manager), \
         patch.object(server, "fetch_media_metadata", return_value={"title": "Canceled early"}) as metadata, \
         patch.object(server.subprocess, "Popen") as popen:
        server.download(job)

    metadata.assert_called_once_with(job["url"], job["id"])
    popen.assert_not_called()
    manager.complete_download.assert_called_once()
    assert manager.complete_download.call_args.args[0]["status"] == "canceled"


def test_completed_process_wins_over_late_cancel_request():
    class FakeStdout:
        def readline(self):
            return ""

    class FakeProcess:
        stdout = FakeStdout()

        def poll(self):
            return 0

    manager = MagicMock()
    manager.current_download = {}
    manager.set_current_download.side_effect = lambda info: setattr(manager, "current_download", info)
    manager.consume_cancellation.side_effect = [False, True]
    job = server.create_queue_job("https://example.com/completed-before-cancel", "best", "web")

    with patch.object(server, "download_manager", manager), \
         patch.object(server, "fetch_media_metadata", return_value={"title": "Completed item"}), \
         patch.object(server, "find_existing_download", return_value=None), \
         patch.object(server, "build_youtube_dl_cmd", return_value=["yt-dlp"]), \
         patch.object(server, "build_completed_history_item", return_value={"status": "completed"}), \
         patch.object(server.subprocess, "Popen", return_value=FakeProcess()):
        server.download(job)

    manager.complete_download.assert_not_called()
    manager.complete_downloads.assert_called_once_with([{"status": "completed"}])


def test_failed_history_uses_non_success_websocket_event():
    manager = server.GlobalDownloadManager()
    manager.set_current_download({"job_id": "failed-job", "status": "downloading"})
    observed_runtime = []

    def capture_event(_message):
        observed_runtime.append((manager.current_download, manager.is_downloading))

    with patch.object(manager, "save_history"), \
         patch.object(manager, "broadcast_to_all_clients", side_effect=capture_event) as broadcast:
        manager.complete_download({
            "uuid": "failed-job",
            "url": "https://youtu.be/failed",
            "resolution": "best",
            "status": "failed",
            "failure_code": "network",
        })

    payload = broadcast.call_args.args[0]
    assert payload.startswith("[HISTORY_UPDATED], ")
    assert '"failure_code": "network"' in payload
    assert observed_runtime == [(None, False)]


def test_history_restore_logs_do_not_include_private_titles(capsys):
    manager = server.GlobalDownloadManager()
    private_item = {
        "uuid": "private-history",
        "title": "https://private.example/media?token=secret",
        "url": "https://private.example/media?token=secret",
        "resolution": "best",
    }
    client = object()
    with patch.object(manager, "load_history"), \
         patch.object(manager, "combined_history", return_value=[private_item]), \
         patch.object(server, "safe_websocket_send", return_value=True):
        manager.add_client(client)

    output = capsys.readouterr().out
    assert "Sent history item 0" in output
    assert "private.example" not in output
    assert "secret" not in output


def test_cancel_endpoint_requires_an_active_download(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server.download_manager, "request_active_cancel", return_value=None):
        response = app.post("/youtube-dl/q/active/cancel", status=409)

    assert response.json["code"] == "active_download_not_found"


def test_canceled_history_item_can_be_queued_for_retry(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    canceled = {
        "uuid": "canceled-job",
        "url": "https://youtu.be/retry-canceled",
        "resolution": "720p",
        "status": "canceled",
        "playlist_mode": "single",
        "write_thumbnail": True,
        "section_mode": "full",
    }
    queued = {
        "queued": True,
        "duplicate": False,
        "job": {"position": 1},
        "queue_count": 1,
    }
    with patch.object(server.download_manager, "get_history_item", return_value=canceled), \
         patch.object(server, "enqueue_download", return_value=queued) as enqueue:
        response = app.post("/youtube-dl/history/retry/canceled-job")

    assert response.json["success"] is True
    assert response.json["code"] == "queued"
    enqueue.assert_called_once_with(
        canceled["url"],
        "720p",
        "web",
        server.ws_addr.wsClassVal,
        playlist_mode="single",
        write_thumbnail=True,
        section_mode="full",
    )


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


def test_completed_history_reuses_existing_file_and_original_timestamp(tmp_path):
    filename = "same__Youtube_ABC123.mp4"
    (tmp_path / filename).write_bytes(b"media")
    manager = server.GlobalDownloadManager()
    manager.download_history = [{
        "uuid": "original-row",
        "timestamp": "2026-08-01T09:00:00",
        "url": "https://youtu.be/ABC123",
        "resolution": "best",
        "title": "Original title",
        "filename": filename,
        "media_id": "ABC123",
        "extractor": "Youtube",
        "status": "completed",
    }]

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), patch.object(manager, "save_history"):
        completed = manager.complete_download({
            "uuid": "new-attempt",
            "timestamp": "2026-08-06T10:00:00",
            "url": "https://youtu.be/ABC123?si=tracking",
            "resolution": "best",
            "title": "Updated title",
            "filename": filename,
            "media_id": "ABC123",
            "extractor": "Youtube",
            "status": "completed",
        })

    assert len(manager.download_history) == 1
    assert completed["uuid"] == "original-row"
    assert completed["timestamp"] == "2026-08-01T09:00:00"
    assert completed["title"] == "Updated title"


def test_completed_history_keeps_different_media_with_same_title(tmp_path):
    first_filename = "same__Youtube_FIRST.mp4"
    second_filename = "same__Youtube_SECOND.mp4"
    (tmp_path / first_filename).write_bytes(b"first")
    (tmp_path / second_filename).write_bytes(b"second")
    manager = server.GlobalDownloadManager()
    manager.download_history = [{
        "uuid": "first",
        "timestamp": "2026-08-01T09:00:00",
        "resolution": "best",
        "title": "Same title",
        "filename": first_filename,
        "media_id": "FIRST",
        "extractor": "Youtube",
        "status": "completed",
    }]

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), patch.object(manager, "save_history"):
        manager.complete_download({
            "uuid": "second",
            "resolution": "best",
            "title": "Same title",
            "filename": second_filename,
            "media_id": "SECOND",
            "extractor": "Youtube",
            "status": "completed",
        })

    assert len(manager.download_history) == 2
    assert {item["media_id"] for item in manager.download_history} == {"FIRST", "SECOND"}


def test_completed_history_keeps_full_and_timestamped_versions_separate(tmp_path):
    full_filename = "same__Youtube_ABC123.mp4"
    clip_filename = "same__from_90s__Youtube_ABC123.mp4"
    (tmp_path / full_filename).write_bytes(b"full")
    (tmp_path / clip_filename).write_bytes(b"clip")
    manager = server.GlobalDownloadManager()
    manager.download_history = [{
        "uuid": "full",
        "resolution": "best",
        "filename": full_filename,
        "media_id": "ABC123",
        "extractor": "Youtube",
        "section_mode": "full",
        "section_start": 0,
        "status": "completed",
    }]

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), patch.object(manager, "save_history"):
        manager.complete_download({
            "uuid": "clip",
            "resolution": "best",
            "filename": clip_filename,
            "media_id": "ABC123",
            "extractor": "Youtube",
            "section_mode": "from_timestamp",
            "section_start": 90,
            "status": "completed",
        })

    assert len(manager.download_history) == 2
    assert {item["uuid"] for item in manager.download_history} == {"full", "clip"}


def test_deleted_physical_file_allows_new_history_for_same_media(tmp_path):
    new_filename = "replacement__Youtube_ABC123.mp4"
    (tmp_path / new_filename).write_bytes(b"replacement")
    manager = server.GlobalDownloadManager()
    manager.download_history = [{
        "uuid": "deleted-file-row",
        "timestamp": "2026-08-01T09:00:00",
        "resolution": "best",
        "filename": "deleted__Youtube_ABC123.mp4",
        "media_id": "ABC123",
        "extractor": "Youtube",
        "status": "completed",
    }]

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), patch.object(manager, "save_history"):
        manager.complete_download({
            "uuid": "replacement-row",
            "resolution": "best",
            "filename": new_filename,
            "media_id": "ABC123",
            "extractor": "Youtube",
            "status": "completed",
        })

    assert len(manager.download_history) == 2
    assert manager.download_history[-1]["uuid"] == "replacement-row"


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


def test_worker_continues_to_next_job_after_a_terminal_result(tmp_path):
    first = server.create_queue_job("https://youtu.be/first", "best", "web")
    second = server.create_queue_job("https://youtu.be/second", "audio-mp3", "web")
    original_active = server.active_queue_job
    original_shutdown = server.shutdown_event.is_set()
    with server.dl_q.mutex:
        original_queue = list(server.dl_q.queue)
        original_unfinished = server.dl_q.unfinished_tasks
        server.dl_q.queue.clear()
        server.dl_q.unfinished_tasks = 0

    try:
        server.shutdown_event.clear()
        server.dl_q.put(first)
        server.dl_q.put(second)
        server.dl_q.put(None)
        with patch.object(server, "QUEUE_STATE_FILE", str(tmp_path / "queue.json")), \
             patch.object(server, "download") as download:
            server.dl_worker()

        assert [entry.args[0]["id"] for entry in download.call_args_list] == [first["id"], second["id"]]
        assert server.active_queue_job is None
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


def test_history_normalization_discovers_thumbnail_sidecar(tmp_path):
    media = tmp_path / "example__Youtube_ABC.mp4"
    thumbnail = tmp_path / "example__Youtube_ABC.jpg"
    media.write_bytes(b"media")
    thumbnail.write_bytes(b"image")

    with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)):
        item = server.normalize_history_item({
            "uuid": "sidecar-item",
            "filename": media.name,
            "resolution": "best",
        })
        mounted_names = {mounted["filename"] for mounted in server.list_mounted_file_items()}

    assert item["thumbnail_file"] == thumbnail.name
    assert item["thumbnail_file_exists"] is True
    assert item["thumbnail_local_url"] == "/static/thumbnail/sidecar-item"
    assert thumbnail.name not in mounted_names


def test_thumbnail_sidecar_is_served_and_deleted_with_media(app, tmp_path):
    media = tmp_path / "example__Youtube_ABC.mp4"
    thumbnail = tmp_path / "example__Youtube_ABC.jpg"
    media.write_bytes(b"media")
    thumbnail.write_bytes(b"image")
    history = [{
        "uuid": "sidecar-item",
        "filename": media.name,
        "resolution": "best",
        "status": "completed",
        "thumbnail_file": thumbnail.name,
    }]
    original_history = server.download_manager.download_history
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)

    try:
        server.download_manager.download_history = history
        with patch.object(server, "DOWNFOLDER_DIR", str(tmp_path)), \
             patch.object(server.download_manager, "load_history"), \
             patch.object(server.download_manager, "save_history"):
            preview = app.get("/static/thumbnail/sidecar-item")
            deleted = app.post("/youtube-dl/history/delete-file/sidecar-item")

        assert preview.body == b"image"
        assert deleted.json["deleted_sidecars"] == [thumbnail.name]
        assert not media.exists()
        assert not thumbnail.exists()
    finally:
        server.download_manager.download_history = original_history


def test_frontend_refreshes_history_after_mobile_foreground_and_reconnect():
    source = (MODULE_PATH.parent / "static" / "logical_js" / "logic.js").read_text(encoding="utf-8")
    assert "document.addEventListener('visibilitychange'" in source
    assert "window.addEventListener('pageshow'" in source
    assert "scheduleDashboardRefresh(50)" in source
    assert "historyFetchInFlight" in source
    assert "pendingHistoryRefresh" in source


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
