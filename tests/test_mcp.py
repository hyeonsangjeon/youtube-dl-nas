import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server import (
    API_PATH, MCP_PATH, MAX_BODY_BYTES, TOOLS, BackendError, WebAPI, create_app,
)
from runtime import COMMIT_TIMEOUT_SECONDS, PREVIEW_TIMEOUT_SECONDS, PROXY_READ_TIMEOUT_SECONDS


URL = "http://127.0.0.1:8082" + MCP_PATH
TOKEN = "test-dashboard-token"
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeBackend:
    def __init__(self):
        self.tokens = {TOKEN, "second-token"}
        self.calls = []
        self.overrides = {}

    async def handle(self, request):
        self.calls.append(request)
        path = request.url.path
        if path in self.overrides:
            override = self.overrides[path]
            if isinstance(override, Exception):
                raise override
            if callable(override):
                return await override(request)
            return httpx.Response(override[0], json=override[1], headers=override[2] if len(override) > 2 else {})
        if path == "/health":
            return httpx.Response(200, json={"status": "ok", "app": "youtube-dl-nas"})
        bearer = request.headers.get("authorization", "")
        parts = bearer.split()
        if len(parts) != 2 or parts[0].casefold() != "bearer" or parts[1] not in self.tokens:
            return httpx.Response(401, json={"error": "unauthorized"})
        if path == API_PATH + "/mcp/auth":
            return httpx.Response(200, json={"authenticated": True})
        responses = {
            "/capabilities": {
                "api_version": "1", "batch_limit": 50, "plan_ttl_seconds": 1800,
                "preview_timeout_seconds": PREVIEW_TIMEOUT_SECONDS,
                "commit_timeout_seconds": COMMIT_TIMEOUT_SECONDS,
            },
            "/profiles": {"profiles": [{"id": "best"}, {"id": "audio-mp3"}]},
            "/library": {"items": [{"uuid": "media-1", "relative_path": "movie.mp4", "file_exists": True}]},
            "/downloads": {"queue": [], "active": None, "storage": {"state": "ok"}},
            "/collections": {"collections": [{"id": "collection-1", "name": "Videos"}]},
            "/collections/collection-1": {"collection": {"id": "collection-1"}, "items": [], "batches": []},
            "/plans": {"plan": {"id": "plan-1", "items": [{"id": "item-1", "status": "new"}]}},
            "/plans/plan-1": {"plan": {"id": "plan-1", "items": [{"id": "item-1", "status": "new"}]}},
            "/plans/plan-1/commit": {"batch": {"id": "batch-1"}, "collection": {"id": "collection-1"}},
            "/batches/batch-1": {"batch": {"id": "batch-1", "progress": {"queued": 1}}},
        }
        if request.method == "POST" and path == API_PATH + "/downloads":
            return httpx.Response(202, json={"queued": True, "job_id": "job-1"})
        payload = responses.get(path.removeprefix(API_PATH))
        return httpx.Response(200 if payload else 404, json=payload or {"error": "not_found"})

    def api(self):
        return WebAPI(8081, transport=httpx.MockTransport(self.handle))

    def writes(self):
        return [request for request in self.calls if request.method == "POST"]


@asynccontextmanager
async def asgi_client(backend, headers=None):
    app = create_app(api=backend.api())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8082",
            headers=headers, timeout=5,
        ) as client:
            yield client


@asynccontextmanager
async def sdk_session(client, url=URL):
    with anyio.fail_after(8):
        async with streamable_http_client(url, http_client=client) as (reader, writer, session_id):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=4)) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.version == os.environ.get("APP_VERSION", "26.0906")
                assert session_id() is None
                yield session


async def rpc(client, method, *, params=None, notification=False, headers=None):
    message = {"jsonrpc": "2.0", "method": method}
    if not notification:
        message["id"] = 1
    if params is not None:
        message["params"] = params
    return await client.post(MCP_PATH, json=message, headers=headers)


@pytest.mark.anyio
async def test_official_sdk_initializes_lists_schemas_and_reads_every_resource():
    backend = FakeBackend()
    async with asgi_client(backend, HEADERS) as client, sdk_session(client) as session:
        result = await session.list_tools()
        definitions = {tool.name: tool for tool in result.tools}
        assert set(definitions) == set(TOOLS)
        assert all(tool.inputSchema["additionalProperties"] is False for tool in result.tools)
        assert all("delete" not in name for name in definitions)
        assert definitions["preview_collection"].annotations.readOnlyHint is False
        assert definitions["commit_collection"].annotations.model_dump(exclude_none=True) == {
            "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True,
        }
        preview_schema = definitions["preview_collection"].inputSchema
        assert preview_schema["$defs"]["Candidate"]["additionalProperties"] is False
        assert preview_schema["$defs"]["DateCriteria"]["additionalProperties"] is False
        for name, arguments, key in (
            ("get_capabilities", {}, "api_version"),
            ("list_profiles", {}, "profiles"),
            ("list_library", {"q": "rain & snow", "limit": 5}, "items"),
            ("get_downloads", {}, "queue"),
            ("list_collections", {}, "collections"),
            ("get_collection", {"collection_id": "collection-1"}, "collection"),
            ("get_plan", {"plan_id": "plan-1"}, "plan"),
            ("get_batch", {"batch_id": "batch-1"}, "batch"),
        ):
            response = await session.call_tool(name, arguments)
            assert not response.isError, response
            assert key in response.structuredContent
    library = next(request for request in backend.calls if request.url.path.endswith("/library"))
    assert dict(library.url.params) == {"q": "rain & snow", "limit": "5"}
    assert not backend.writes()
    assert len([request for request in backend.calls if request.url.path.endswith("/mcp/auth")]) >= 11
    assert all(request.headers.get("authorization") == HEADERS["Authorization"] for request in backend.calls)


@pytest.mark.anyio
async def test_enqueue_preview_and_approved_commit_forward_only_typed_api_bodies():
    backend = FakeBackend()
    preview = {
        "name": "September videos", "description": "A client-selected collection",
        "criteria": {"date_from": "2026-09-01", "date_to": "2026-09-06"},
        "resolution": "audio-mp3", "candidates": [{"url": "https://example.com/watch?v=1"}],
    }
    commit = {
        "plan_id": "plan-1", "confirm": True, "create_collection": True,
        "selected_item_ids": ["item-1"], "include_unknown_dates": ["item-1"],
    }
    async with asgi_client(backend, HEADERS) as client, sdk_session(client) as session:
        assert not (await session.call_tool("enqueue_download", {"url": "https://example.com/video"})).isError
        assert not (await session.call_tool("preview_collection", preview)).isError
        first = await session.call_tool("commit_collection", commit)
        second = await session.call_tool("commit_collection", commit)
        assert not first.isError and first.structuredContent == second.structuredContent
        existing = {**commit, "collection_id": "collection-1", "create_collection": False}
        assert not (await session.call_tool("commit_collection", existing)).isError
    writes = backend.writes()
    assert [(request.method, request.url.path) for request in writes] == [
        ("POST", API_PATH + "/downloads"), ("POST", API_PATH + "/plans"),
        ("POST", API_PATH + "/plans/plan-1/commit"),
        ("POST", API_PATH + "/plans/plan-1/commit"),
        ("POST", API_PATH + "/plans/plan-1/commit"),
    ]
    assert json.loads(writes[0].content) == {"url": "https://example.com/video", "resolution": "best"}
    assert json.loads(writes[1].content) == preview
    assert json.loads(writes[2].content) == {
        "create_collection": True, "selected_item_ids": ["item-1"], "include_unknown_dates": ["item-1"],
    }
    assert json.loads(writes[4].content) == {
        "collection_id": "collection-1", "selected_item_ids": ["item-1"], "include_unknown_dates": ["item-1"],
    }
    assert all(request.headers["authorization"] == HEADERS["Authorization"] for request in writes)
    assert writes[1].extensions["timeout"]["read"] == PREVIEW_TIMEOUT_SECONDS
    assert all(request.extensions["timeout"]["read"] == COMMIT_TIMEOUT_SECONDS for request in writes[2:])
    assert all(request.extensions["timeout"]["connect"] == 2 for request in writes)


def test_batch_deadlines_allow_bounded_preview_and_fast_local_commit():
    assert PREVIEW_TIMEOUT_SECONDS == 900
    assert COMMIT_TIMEOUT_SECONDS == 120
    assert PROXY_READ_TIMEOUT_SECONDS == 960
    assert PROXY_READ_TIMEOUT_SECONDS == max(PREVIEW_TIMEOUT_SECONDS, COMMIT_TIMEOUT_SECONDS) + 60


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
@pytest.mark.parametrize("authorization", [None, "", "Basic dXNlcjpwYXNz", "Bearer wrong-token"])
async def test_every_transport_request_requires_bearer_not_dashboard_cookie(method, authorization):
    backend = FakeBackend()
    headers = {"Cookie": "auth=dashboard-session", "Accept": "application/json, text/event-stream"}
    if authorization is not None:
        headers["Authorization"] = authorization
    async with asgi_client(backend, headers) as client:
        response = await client.request(method, MCP_PATH + "?token=" + TOKEN, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer ")
    assert TOKEN not in response.text
    assert all("cookie" not in request.headers for request in backend.calls)


@pytest.mark.anyio
async def test_revocation_is_checked_on_notifications_and_subsequent_requests():
    backend = FakeBackend()
    async with asgi_client(backend, HEADERS) as client:
        good = await rpc(client, "notifications/initialized", notification=True)
        assert good.status_code == 202
        backend.tokens.remove(TOKEN)
        notification = await rpc(client, "notifications/initialized", notification=True)
        tools = await rpc(client, "tools/list")
        get = await client.get(MCP_PATH)
    assert [notification.status_code, tools.status_code, get.status_code] == [401, 401, 401]
    assert len(backend.calls) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["Bearer ", "bearer ", "bEaReR ", "Bearer   "])
async def test_original_authorization_value_is_forwarded_without_normalization(prefix):
    backend = FakeBackend()
    authorization = prefix + TOKEN
    async with asgi_client(backend, {**HEADERS, "Authorization": authorization}) as client:
        async with sdk_session(client) as session:
            assert not (await session.call_tool("get_capabilities")).isError
    assert backend.calls
    assert all(request.headers["authorization"] == authorization for request in backend.calls)


@pytest.mark.anyio
async def test_duplicate_authorization_headers_are_rejected():
    backend = FakeBackend()
    async with asgi_client(backend) as client:
        response = await client.post(MCP_PATH, headers=[
            ("Authorization", "Bearer " + TOKEN), ("Authorization", "Bearer second-token"),
        ], json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
    assert not backend.calls


@pytest.mark.anyio
async def test_concurrent_clients_do_not_share_bearer_context_or_upstream_cookies():
    backend = FakeBackend()

    async def downloads(request):
        await anyio.sleep(0.01 if request.headers["authorization"].endswith(TOKEN) else 0.02)
        return httpx.Response(200, json={"caller": request.headers["authorization"]}, headers={
            "Set-Cookie": "upstream-session=must-not-be-reused; Path=/",
        })

    backend.overrides[API_PATH + "/downloads"] = downloads
    app = create_app(api=backend.api())

    async def read(token):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": "Bearer " + token, "Cookie": "auth=not-forwarded"},
        ) as client, sdk_session(client) as session:
            first = await session.call_tool("get_downloads")
            second = await session.call_tool("get_downloads")
            assert first.structuredContent == second.structuredContent
            return first.structuredContent["caller"]

    async with app.router.lifespan_context(app):
        assert await asyncio.gather(read(TOKEN), read("second-token")) == [
            "Bearer " + TOKEN, "Bearer second-token",
        ]
    assert all("cookie" not in request.headers for request in backend.calls)


@pytest.mark.anyio
@pytest.mark.parametrize("override", [
    (200, {"authenticated": False}), (200, {"authenticated": "true"}), (200, {}),
    (404, {"error": "unknown endpoint"}), (500, {"trace": "SECRET STACK"}),
    (302, {}, {"Location": "https://attacker.invalid/collect"}),
    httpx.ConnectError("SECRET CONNECTION DETAILS"),
])
async def test_auth_fails_closed_when_backend_is_unknown_unreachable_or_redirects(override):
    backend = FakeBackend()
    backend.overrides[API_PATH + "/mcp/auth"] = override
    async with asgi_client(backend, HEADERS) as client:
        response = await rpc(client, "tools/list")
    assert response.status_code == 503
    assert "SECRET" not in response.text
    assert len(backend.calls) == 1
    assert backend.calls[0].url.host == "127.0.0.1"


@pytest.mark.anyio
@pytest.mark.parametrize("override_path,override", [
    (None, None),
    ("/health", (200, {"status": "ok", "app": "some-other-service"})),
    ("/health", (503, {"status": "not-ready"})),
    ("/health", httpx.ConnectError("private details")),
    (API_PATH + "/mcp/auth", (404, {})),
    (API_PATH + "/mcp/auth", (403, {})),
    (API_PATH + "/mcp/auth", (200, {"authenticated": True})),
])
async def test_minimal_public_health_requires_web_and_auth_endpoint_readiness(override_path, override):
    backend = FakeBackend()
    if override_path:
        backend.overrides[override_path] = override
    async with asgi_client(backend) as client:
        response = await client.get(MCP_PATH + "/health", headers={"Cookie": "auth=no"})
    assert response.status_code == (503 if override_path else 200)
    assert response.json() == {"status": "unavailable" if override_path else "ok"}
    assert all("authorization" not in request.headers and "cookie" not in request.headers for request in backend.calls)


@pytest.mark.anyio
@pytest.mark.parametrize("name,arguments", [
    ("enqueue_download", {"url": "/downfolder/file.mp4"}),
    ("enqueue_download", {"url": "file:///etc/passwd"}),
    ("enqueue_download", {"url": "https://user:pass@example.com/video"}),
    ("enqueue_download", {"url": "https://example.com/video", "output": "/downfolder/file"}),
    ("enqueue_download", {"url": "https://example.com/video", "exec": "touch marker"}),
    ("enqueue_download", {"url": "https://example.com/video", "resolution": "best; --exec=bad"}),
    ("preview_collection", {"name": "../escape", "candidates": [{"url": "https://example.com/video"}]}),
    ("preview_collection", {"name": "Videos", "candidates": [{"url": "https://example.com/video", "path": "/etc"}]}),
    ("preview_collection", {"name": "Videos", "candidates": [{"url": "https://example.com/video"}],
                            "criteria": {"date_from": "2026-02-30"}}),
    ("preview_collection", {"name": "Videos", "candidates": [{"url": "https://example.com/video"}],
                            "criteria": {"date_from": "2026-09-06", "date_to": "2026-09-01"}}),
    ("preview_collection", {"name": "Videos", "candidates": [], "physical_directory": "/etc"}),
    ("get_collection", {"collection_id": "../../mcp/auth"}),
    ("get_plan", {"plan_id": "plan%2f1"}),
    ("get_batch", {"batch_id": "batch-1?token=leak"}),
    ("get_downloads", {"path": "/downfolder"}),
    ("list_library", {"limit": "100"}),
])
async def test_unsafe_or_extra_arguments_never_reach_the_api(name, arguments):
    backend = FakeBackend()
    async with asgi_client(backend, HEADERS) as client, sdk_session(client) as session:
        result = await session.call_tool(name, arguments)
    assert result.isError
    assert result.structuredContent["error"]["code"] == "invalid_arguments"
    assert all(request.url.path.endswith("/mcp/auth") for request in backend.calls)


@pytest.mark.anyio
@pytest.mark.parametrize("change", [
    {"confirm": False}, {"confirm": 1}, {"confirm": None},
    {"create_collection": False}, {"collection_id": "collection-1"},
    {"selected_item_ids": []}, {"selected_item_ids": ["item-1", "item-1"]},
    {"include_unknown_dates": ["not-selected"]},
    {"physical_directory": "/downfolder/unapproved"},
])
async def test_commit_requires_explicit_approval_exact_target_and_safe_selection(change):
    backend = FakeBackend()
    arguments = {
        "plan_id": "plan-1", "confirm": True, "create_collection": True,
        "selected_item_ids": ["item-1"], **change,
    }
    async with asgi_client(backend, HEADERS) as client, sdk_session(client) as session:
        result = await session.call_tool("commit_collection", arguments)
    assert result.isError
    assert not backend.writes()


@pytest.mark.anyio
@pytest.mark.parametrize("status,code", [(401, "unauthorized"), (409, "conflict"), (410, "plan_expired"),
                                       (429, "limit_exceeded"), (500, "backend_unavailable"),
                                       (302, "backend_unavailable")])
async def test_tool_errors_are_sanitized_and_mutations_are_never_retried(status, code):
    backend = FakeBackend()
    backend.overrides[API_PATH + "/downloads"] = (
        status, {"error": "raw stack /private/path SECRET " + TOKEN},
        {"Location": "https://attacker.invalid/"},
    )
    async with asgi_client(backend, HEADERS) as client, sdk_session(client) as session:
        result = await session.call_tool("enqueue_download", {"url": "https://example.com/video"})
    assert result.isError
    assert result.structuredContent["error"]["code"] == code
    serialized = result.model_dump_json()
    assert "SECRET" not in serialized and TOKEN not in serialized and "/private" not in serialized
    assert len(backend.writes()) == 1


@pytest.mark.anyio
async def test_loopback_calls_ignore_proxy_environment_and_have_total_deadlines(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://attacker.invalid:8080")
    backend = FakeBackend()

    async def slow(_request):
        await anyio.sleep(1)
        return httpx.Response(200, json={"status": "ok"})

    backend.overrides["/slow"] = slow
    with anyio.fail_after(1), pytest.raises(BackendError, match="web API is unavailable"):
        await backend.api().request("GET", "/slow", timeout=0.02)
    assert backend.calls[0].url.host == "127.0.0.1"


@pytest.mark.anyio
@pytest.mark.parametrize("origin,public_host,status", [
    ("https://nas.example", "nas.example", 200),
    ("https://nas.example:443", "nas.example", 200),
    ("http://nas.example:8080", "nas.example:8080", 200),
    ("https://attacker.invalid", "nas.example", 403),
    ("null", "nas.example", 403),
    ("https://nas.example/path", "nas.example", 403),
    ("https://nas.example@attacker.invalid", "nas.example", 403),
])
async def test_public_origin_is_checked_before_sdk_loopback_host_validation(origin, public_host, status):
    backend = FakeBackend()
    async with asgi_client(backend, HEADERS) as client:
        response = await rpc(client, "tools/list", headers={
            "Origin": origin, "X-Forwarded-Host": public_host,
        })
    assert response.status_code == status


@pytest.mark.anyio
async def test_sdk_rejects_bad_host_and_oversized_body_and_unknown_tools():
    backend = FakeBackend()
    async with asgi_client(backend, HEADERS) as client:
        bad_host = await rpc(client, "tools/list", headers={"Host": "attacker.invalid"})
        oversized = await client.post(MCP_PATH, content=b"x" * (MAX_BODY_BYTES + 1), headers={
            "Content-Type": "application/json",
        })
        unknown = await rpc(client, "tools/call", params={"name": "delete_file", "arguments": {}})
    assert bad_host.status_code == 421
    assert oversized.status_code == 413
    assert unknown.json()["result"]["structuredContent"]["error"]["code"] == "unknown_tool"
    assert not backend.writes()


@pytest.mark.anyio
async def test_real_uvicorn_socket_with_official_streamable_http_client():
    backend = FakeBackend()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(
            create_app(mcp_port=port, api=backend.api()), log_level="error",
            access_log=False, proxy_headers=False, timeout_graceful_shutdown=1,
        ))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                await anyio.sleep(0.02)
            assert server.started
            async with httpx.AsyncClient(headers=HEADERS, trust_env=False, timeout=4) as client:
                async with sdk_session(client, f"http://127.0.0.1:{port}{MCP_PATH}") as session:
                    response = await session.call_tool("get_capabilities")
                    assert response.structuredContent["api_version"] == "1"
                health = await client.get(f"http://127.0.0.1:{port}{MCP_PATH}/health")
                assert health.status_code == 200
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.mark.anyio
async def test_real_web_api_issues_revokes_hashed_tokens_and_preserves_env_compatibility(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        web_port = listener.getsockname()[1]
    auth_file = tmp_path / "Auth.json"
    auth_file.write_text("{}", encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "AUTH_FILE": str(auth_file), "STATE_DIR": str(tmp_path / "state"),
        "DOWNLOAD_DIR": str(tmp_path / "downloads"), "TMPDIR": str(tmp_path),
        "YDLNAS_WEB_HOST": "127.0.0.1", "YDLNAS_WEB_PORT": str(web_port),
        "MY_ID": "mcp-integration", "MY_PW": "mcp-integration-password",
        "YDLNAS_API_TOKEN": "compatibility-token", "TERMS_ACCEPTED": "Y",
        "YDLNAS_ALLOW_PRIVATE_SOURCES": "false",
    })
    process = subprocess.Popen(
        [sys.executable, "-u", str(root / "youtube-dl-server.py")], cwd=root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        base = f"http://127.0.0.1:{web_port}"
        async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=2) as dashboard:
            deadline = time.monotonic() + 8
            while True:
                try:
                    if (await dashboard.get("/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=1)
                    pytest.fail(f"Web API exited: {stdout}\n{stderr}")
                assert time.monotonic() < deadline, "Web API did not become ready"
                await anyio.sleep(0.05)
            login = await dashboard.post("/login", data={"id": env["MY_ID"], "myPw": env["MY_PW"]})
            assert login.status_code in (302, 303)
            issued = await dashboard.post(API_PATH + "/connections", json={"name": "MCP integration"})
            assert issued.status_code == 200
            token = issued.json()["token"]
            connection_id = issued.json()["connection"]["id"]
            app = create_app(web_port=web_port)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8082",
                    headers={**HEADERS, "Authorization": "Bearer " + token},
                ) as client:
                    async with sdk_session(client) as session:
                        capabilities = await session.call_tool("get_capabilities")
                        assert capabilities.structuredContent["api_version"] == "1"
                        assert capabilities.structuredContent["preview_timeout_seconds"] == PREVIEW_TIMEOUT_SECONDS
                        assert capabilities.structuredContent["commit_timeout_seconds"] == COMMIT_TIMEOUT_SECONDS
                        profiles = await session.call_tool("list_profiles")
                        supported = TOOLS["enqueue_download"].definition("enqueue_download").inputSchema["properties"]["resolution"]["enum"]
                        assert all(profile["id"] in supported for profile in profiles.structuredContent["profiles"])
                        for name in ("list_library", "list_collections", "get_downloads"):
                            assert not (await session.call_tool(name)).isError
                        preview = await session.call_tool("preview_collection", {
                            "name": "No-network preview",
                            "criteria": {"date_from": "2020-01-01", "date_to": "2026-09-06"},
                            "candidates": [{"url": "http://127.0.0.1/private"}],
                        })
                        assert not preview.isError, preview
                        plan = preview.structuredContent["plan"]
                        assert plan["items"][0]["status"] == "invalid"
                        saved = await session.call_tool("get_plan", {"plan_id": plan["id"]})
                        assert saved.structuredContent["plan"]["id"] == plan["id"]
                        rejected = await session.call_tool("commit_collection", {
                            "plan_id": plan["id"], "confirm": True, "create_collection": True,
                            "selected_item_ids": ["not-in-this-plan"],
                        })
                        assert rejected.isError
                        downloads = await session.call_tool("get_downloads")
                        collections = await session.call_tool("list_collections")
                        assert downloads.structuredContent["queue"] == []
                        assert collections.structuredContent["collections"] == []
                    assert (await client.get(MCP_PATH + "/health")).status_code == 200
                    revoked = await dashboard.delete(API_PATH + "/connections/" + connection_id)
                    assert revoked.status_code == 200
                    denied = await rpc(client, "notifications/initialized", notification=True)
                    assert denied.status_code == 401
                    client.headers["Authorization"] = "Bearer " + env["YDLNAS_API_TOKEN"]
                    async with sdk_session(client) as session:
                        assert not (await session.call_tool("get_capabilities")).isError
    finally:
        process.terminate()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)
