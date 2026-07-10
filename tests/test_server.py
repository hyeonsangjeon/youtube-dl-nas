import importlib.util
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
SPEC = importlib.util.spec_from_file_location("youtube_dl_nas_server", MODULE_PATH)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


@pytest.fixture
def app():
    return TestApp(default_app())


def test_health_and_manifest_are_public(app):
    health = app.get("/health")
    assert health.json["status"] == "ok"
    assert health.json["version"] == "26.0710"

    manifest = app.get("/manifest.webmanifest")
    assert manifest.json["share_target"]["action"] == "/youtube-dl/share-target"
    assert manifest.json["share_target"]["method"] == "POST"


def test_queue_endpoints_require_login(app):
    assert app.get("/youtube-dl/q", status=403).json["msg"] == "Unauthorized"
    assert app.post_json(
        "/youtube-dl/q",
        {"url": "https://youtu.be/example", "resolution": "best"},
        status=403,
    ).json["msg"] == "Unauthorized"


def test_login_rejects_empty_credentials_when_account_is_unconfigured(app):
    with patch.object(server, "load_auth_data", return_value={"MY_ID": "", "MY_PW": "", "SECRET_KEY": "test"}):
        response = app.post("/login", {"id": "", "myPw": "", "next": "/youtube-dl"})
    assert "id or password is not correct" in response.text


def test_rest_api_keeps_id_password_auth(app):
    with patch.object(server, "enqueue_download") as enqueue:
        response = app.post_json("/youtube-dl/rest", {
            "url": "https://youtu.be/example",
            "resolution": "best",
            "id": "tester",
            "pw": "secret",
        })
    assert response.json["success"] is True
    enqueue.assert_called_once_with("https://youtu.be/example", "best", "api", "")


def test_rest_api_accepts_optional_bearer_token(app):
    with patch.object(server, "enqueue_download") as enqueue:
        response = app.post_json(
            "/youtube-dl/rest",
            {"url": "https://youtu.be/example", "resolution": "audio-m4a"},
            headers={"Authorization": "Bearer integration-token"},
        )
    assert response.json["success"] is True
    enqueue.assert_called_once()


def test_rest_api_rejects_empty_or_invalid_credentials(app):
    app.post_json(
        "/youtube-dl/rest",
        {"url": "https://youtu.be/example", "resolution": "best"},
        status=403,
    )
    app.post_json(
        "/youtube-dl/rest",
        {"url": "https://youtu.be/example", "resolution": "best", "id": "tester", "pw": "wrong"},
        status=403,
    )


def test_login_then_share_target_queues_url(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)
    with patch.object(server, "enqueue_download") as enqueue:
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
    assert "after_move:__YDLNAS_FILE__:%(filepath)s" in command
    assert "--exec" not in command


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
    finally:
        with server.dl_q.mutex:
            server.dl_q.queue.clear()
            server.dl_q.queue.extend(original_queue)
