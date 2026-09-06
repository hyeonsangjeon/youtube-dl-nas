import copy
import base64
import io
import json
import os
import socket
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from queue import Queue
from threading import Event, Thread, get_ident
from unittest.mock import MagicMock

import pytest
from bottle import default_app
from webtest import TestApp

from test_server import server, stable_public_source_network
import collections_backend as backend


BASE = "/youtube-dl/api/v1"
AUTH = {"Authorization": "Bearer integration-token"}
REAL_FETCH_MEDIA_METADATA = server.fetch_media_metadata
REAL_START_DOWNLOAD_THREAD = server.start_download_thread_if_needed


@pytest.fixture(autouse=True)
def isolated_backend(tmp_path, monkeypatch):
    downloads = tmp_path / "downloads"
    state = tmp_path / "state"
    downloads.mkdir()
    state.mkdir()
    monkeypatch.setattr(server, "DOWNFOLDER_DIR", str(downloads))
    monkeypatch.setattr(server, "APP_STATE_FILE", str(state / "app.json"))
    monkeypatch.setattr(server, "QUEUE_STATE_FILE", str(state / "queue.json"))
    monkeypatch.setattr(server, "COLLECTIONS_STATE_FILE", str(state / "collections.json"))
    monkeypatch.setattr(server, "CONNECTIONS_STATE_FILE", str(state / "connections.json"))
    monkeypatch.setattr(server, "APP_COOKIES_FILE", str(state / "cookies.txt"))
    monkeypatch.setattr(server, "YTDLP_COOKIES_FILE", "")
    monkeypatch.setattr(server, "dl_q", Queue())
    monkeypatch.setattr(server, "active_queue_job", None)
    monkeypatch.setattr(server, "queue_state_loaded", False)
    monkeypatch.setattr(server, "queue_restore_count", 0)
    monkeypatch.setattr(server, "shutdown_event", Event())
    monkeypatch.setattr(server, "worker_failed_event", Event())
    monkeypatch.setattr(server, "download_thread", None)
    monkeypatch.setattr(server, "start_download_thread_if_needed", MagicMock())
    monkeypatch.setattr(server.download_manager, "history_file", str(state / "history.json"))
    monkeypatch.setattr(server.download_manager, "download_history", [])
    monkeypatch.setattr(server.download_manager, "current_download", None)
    monkeypatch.setattr(server.download_manager, "is_downloading", False)
    monkeypatch.setattr(server.download_manager, "connected_clients", set())
    monkeypatch.setattr(server.download_manager, "client_hubs", {})
    monkeypatch.setattr(server.download_manager, "cancel_requested_job_id", None)
    monkeypatch.setattr(server, "get_storage_status", lambda: {"blocking": False, "state": "ok"})
    monkeypatch.setattr(server, "collections_service", backend.CollectionService(server.__dict__, server.COLLECTIONS_STATE_FILE))
    monkeypatch.setattr(server, "connections_store", backend.ConnectionStore(server.CONNECTIONS_STATE_FILE))
    monkeypatch.setattr(server, "fetch_media_metadata", lambda url, *args, **kwargs: {
        "id": url.rsplit("/", 1)[-1], "extractor_key": "Youtube",
        "title": "Trusted title", "upload_date": "20260810",
    })
    return downloads, state


@pytest.fixture
def client():
    return TestApp(default_app())


@pytest.fixture
def live_gevent_server():
    import gevent
    from gevent.pywsgi import WSGIServer
    from geventwebsocket.handler import WebSocketHandler

    ready = Queue()
    running = {}

    def serve():
        try:
            web = WSGIServer(("127.0.0.1", 0), default_app(), handler_class=WebSocketHandler, log=None, error_log=None)
            web.start()
            running.update(server=web, hub=gevent.get_hub())
            ready.put(web.server_port)
            web.serve_forever()
        except BaseException as error:
            ready.put(error)

    thread = Thread(target=serve, daemon=True)
    thread.start()
    port = ready.get(timeout=5)
    if isinstance(port, BaseException):
        raise port
    try:
        yield {"port": port, "thread": thread, "hub": running["hub"]}
    finally:
        def stop():
            pool = getattr(running["hub"], "_ydlnas_auth_pool", None)
            if pool is not None:
                pool.kill()
            running["server"].stop()

        running["hub"].loop.run_callback_threadsafe(lambda: gevent.spawn(stop))
        thread.join(timeout=5)
        assert not thread.is_alive()


def loopback_json(port, path, payload=None, headers=None, timeout=2):
    connection = HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        body = json.dumps(payload) if payload is not None else None
        headers = {**(headers or {})}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
        result = connection.getresponse()
        return result.status, json.loads(result.read())
    finally:
        connection.close()


def login(client):
    client.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)


def make_plan(client, candidates=None, **overrides):
    payload = {
        "name": "Summer media", "description": "Curated videos",
        "criteria": {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        "resolution": "best", "candidates": candidates or [{"url": "https://youtu.be/first"}],
    }
    payload.update(overrides)
    return client.post_json(BASE + "/plans", payload, headers=AUTH).json["plan"]


def approve(client, plan, **overrides):
    payload = {
        "create_collection": True,
        "selected_item_ids": [item["id"] for item in plan["items"] if item["status"] not in {"invalid", "outside_date_range"}],
    }
    payload.update(overrides)
    return client.post_json(BASE + f"/plans/{plan['id']}/commit", payload, headers=AUTH).json


def finish_job(downloads, job, name="video.mp4", upload_date="2026-08-10"):
    relative = (job.get("target_relative_directory") + "/" if job.get("target_relative_directory") else "") + name
    path = downloads / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media")
    return server.download_manager.complete_download({
        "uuid": job["id"], "job_id": job["id"], "url": job["url"], "resolution": job["resolution"],
        "title": "Completed title", "relative_path": relative, "filename": name, "status": "completed",
        "collection_id": job.get("collection_id"), "batch_id": job.get("batch_id"),
        "upload_date": upload_date,
    })


def restart_backend(monkeypatch):
    monkeypatch.setattr(server, "dl_q", Queue())
    monkeypatch.setattr(server, "active_queue_job", None)
    monkeypatch.setattr(server, "queue_state_loaded", False)
    server.download_manager.load_history()
    service = backend.CollectionService(server.__dict__, server.COLLECTIONS_STATE_FILE)
    monkeypatch.setattr(server, "collections_service", service)
    server.load_persisted_queue()
    service.reconcile()
    return service


def test_capabilities_profiles_downloads_and_library_are_versioned(client):
    assert client.get(BASE + "/capabilities", status=401).json["code"] == "unauthorized"
    capability = client.get(BASE + "/capabilities", headers=AUTH).json
    assert capability["api_version"] == "1"
    assert capability["batch_limit"] == 25
    assert capability["plan_ttl_seconds"] == 1800
    assert capability["preview_timeout_seconds"] == 900
    assert capability["preview_work_timeout_seconds"] == 840
    assert capability["commit_timeout_seconds"] == 120
    assert {"best", "compatible-mp4", "720p", "audio-m4a"} <= {
        profile["id"] for profile in client.get(BASE + "/profiles", headers=AUTH).json["profiles"]
    }
    assert client.get(BASE + "/library", headers=AUTH).json["items"] == []
    result = client.post_json(BASE + "/downloads", {"url": "https://youtu.be/direct"}, headers=AUTH).json
    duplicate = client.post_json(BASE + "/downloads", {"url": "https://youtu.be/direct"}, headers=AUTH).json
    assert duplicate["job"]["id"] == result["job"]["id"]
    assert duplicate["code"] == "duplicate_queue"
    assert client.get(BASE + "/downloads", headers=AUTH).json["queue"][0]["id"] == result["job"]["id"]


@pytest.mark.parametrize("configured, expected", [("0", 1), ("-10", 1), ("1000", 100), ("3", 3), ("invalid", 25)])
def test_batch_limit_is_clamped(monkeypatch, client, configured, expected):
    monkeypatch.setenv("YDLNAS_MCP_BATCH_LIMIT", configured)
    assert client.get(BASE + "/capabilities", headers=AUTH).json["batch_limit"] == expected


def test_preview_is_bounded_and_has_no_media_or_queue_side_effects(client, isolated_backend, monkeypatch):
    downloads, state = isolated_backend
    fetch = MagicMock(return_value={"id": "one", "title": "Trusted", "upload_date": "20260810"})
    monkeypatch.setattr(server, "fetch_media_metadata", fetch)
    monkeypatch.setenv("YDLNAS_MCP_BATCH_LIMIT", "1")
    client.post_json(BASE + "/plans", {
        "name": "Too many", "candidates": [{"url": "https://youtu.be/one"}, {"url": "https://youtu.be/two"}],
    }, headers=AUTH, status=400)
    fetch.assert_not_called()
    plan = make_plan(client)
    assert plan["items"][0]["title"] == "Trusted"
    assert list(downloads.iterdir()) == []
    assert server.pending_queue_jobs() == []
    assert not (state / "queue.json").exists()
    assert json.loads((state / "collections.json").read_text())["version"] == 1
    server.start_download_thread_if_needed.assert_not_called()


def test_preview_classifies_trusted_metadata_not_hints(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    (downloads / "existing.mp4").write_bytes(b"existing")
    server.download_manager.download_history = [{
        "uuid": "existing", "filename": "existing.mp4", "url": "https://youtu.be/saved",
        "resolution": "best", "status": "completed",
    }]
    server.download_manager.save_history()
    server.enqueue_download("https://youtu.be/queued", "best", "web")
    metadata = {
        "new": {"upload_date": "20260812"},
        "unknown": {},
        "outside": {"upload_date": "20200101"},
        "saved": {"upload_date": "20260810"},
        "queued": {"upload_date": "20260811"},
    }
    monkeypatch.setattr(server, "fetch_media_metadata", lambda url, **kwargs: {
        "id": url.rsplit("/", 1)[-1], "title": "Verified", "extractor_key": "Youtube",
        **metadata[url.rsplit("/", 1)[-1]],
    })
    candidates = [
        {"url": f"https://youtu.be/{key}", "title": "Untrusted", "upload_date": "20260805"}
        for key in metadata
    ] + [{"url": "file:///private/secret"}]
    plan = make_plan(client, candidates)
    assert [item["status"] for item in plan["items"]] == [
        "new", "date_unknown", "outside_date_range", "already_downloaded", "already_queued", "invalid",
    ]
    assert all(item["title"] == "Verified" for item in plan["items"][:-1])
    assert plan["items"][1]["upload_date"] is None
    assert plan["items"][2]["upload_date"] == "2020-01-01"
    assert client.get(BASE + f"/plans/{plan['id']}", headers=AUTH).json["plan"]["items"] == plan["items"]


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/playlist?list=PL123", "https://www.youtube.com/@creator/videos",
    "https://www.youtube.com/watch?v=one&list=PL123", "https://example.com/channels/creator",
])
def test_preview_rejects_expanding_urls_without_fetch(client, monkeypatch, url):
    fetch = MagicMock()
    monkeypatch.setattr(server, "fetch_media_metadata", fetch)
    plan = make_plan(client, [{"url": url}])
    assert plan["items"][0]["status"] == "invalid"
    assert plan["items"][0]["reason"] == "direct_urls_only"
    fetch.assert_not_called()


def test_preview_rejects_playlist_metadata_and_duplicate_candidates(client, monkeypatch):
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "_type": "playlist", "entries": [{"title": "First", "upload_date": "20260801"}],
    })
    assert make_plan(client)["items"][0]["status"] == "invalid"
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "id": "one", "extractor_key": "Youtube", "upload_date": "20260801", "title": "First",
    })
    plan = make_plan(client, [{"url": "https://youtu.be/one"}, {"url": "https://youtu.be/one?si=tracking"}])
    assert [item["status"] for item in plan["items"]] == ["new", "invalid"]
    assert plan["items"][1]["reason"] == "duplicate_candidate"


@pytest.mark.parametrize("criteria", [
    {"date_from": "2026-02-30"}, {"date_to": "20260801"}, {"date_from": 20260801},
    {"date_from": "2026-09-01", "date_to": "2026-08-01"}, {"unexpected": "2026-08-01"},
])
def test_preview_rejects_invalid_criteria(client, criteria):
    result = client.post_json(BASE + "/plans", {
        "name": "Invalid", "criteria": criteria, "candidates": [{"url": "https://youtu.be/one"}],
    }, headers=AUTH, status=400).json
    assert result["code"] == "invalid_date_range"


def test_commit_requires_explicit_unknown_date_approval_and_selection(client, monkeypatch):
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {"title": "No date", "id": "unknown"})
    plan = make_plan(client)
    item_id = plan["items"][0]["id"]
    assert plan["items"][0]["status"] == "date_unknown"
    url = BASE + f"/plans/{plan['id']}/commit"
    assert client.post_json(url, {"create_collection": True}, headers=AUTH, status=400).json["code"] == "selection_required"
    assert client.post_json(url, {
        "create_collection": True, "selected_item_ids": [item_id],
    }, headers=AUTH, status=400).json["code"] == "unknown_date_approval_required"
    assert client.post_json(url, {
        "create_collection": True, "selected_item_ids": [item_id], "include_unknown_dates": ["not-selected"],
    }, headers=AUTH, status=400).json["code"] == "invalid_selection"
    receipt = approve(client, plan, include_unknown_dates=[item_id])
    assert receipt["batch"]["progress"]["queued"] == 1
    assert server.pending_queue_jobs()[0]["date_policy"]["include_unknown_date"] is True


def test_known_outside_items_cannot_be_committed_even_with_override(client, monkeypatch):
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {"id": "old", "upload_date": "19900101"})
    plan = make_plan(client)
    item_id = plan["items"][0]["id"]
    result = client.post_json(BASE + f"/plans/{plan['id']}/commit", {
        "create_collection": True, "selected_item_ids": [item_id], "include_unknown_dates": [item_id],
    }, headers=AUTH, status=400).json
    assert result["code"] == "ineligible_plan_item"
    assert server.pending_queue_jobs() == []
    assert server.collections_service.list_collections() == []


def test_commit_journals_trusted_preview_without_network_and_checks_expiry(client, monkeypatch):
    plan = make_plan(client)
    expiring = make_plan(client, [{"url": "https://youtu.be/expiring"}])
    fetch = MagicMock(side_effect=AssertionError("Commit must not refetch network metadata"))
    redirects = MagicMock(side_effect=AssertionError("Commit must not probe source redirects"))
    dns = MagicMock(side_effect=AssertionError("Commit must not resolve source DNS"))
    library = MagicMock(wraps=server.download_manager.combined_history)
    monkeypatch.setattr(server, "fetch_media_metadata", fetch)
    monkeypatch.setattr(server, "validate_source_redirects", redirects)
    monkeypatch.setattr(server, "resolve_source_addresses", dns)
    monkeypatch.setattr(server.download_manager, "combined_history", library)
    result = approve(client, plan)
    assert result["batch"]["progress"]["queued"] == 1
    assert server.pending_queue_jobs()[0]["upload_date"] == plan["items"][0]["upload_date"]
    assert server.pending_queue_jobs()[0]["title"] == plan["items"][0]["title"]
    library.assert_called_once()
    fetch.assert_not_called()
    redirects.assert_not_called()
    dns.assert_not_called()
    expiry = server.collections_service.state["plans"][expiring["id"]]["expires_at_epoch"]
    monkeypatch.setattr(backend.time, "time", lambda: expiry + 1)
    assert client.get(BASE + f"/plans/{expiring['id']}", headers=AUTH).json["plan"]["expired"]
    assert client.post_json(BASE + f"/plans/{expiring['id']}/commit", {
        "create_collection": True, "selected_item_ids": [expiring["items"][0]["id"]],
    }, headers=AUTH, status=410).json["code"] == "plan_expired"


def test_commits_are_concurrently_idempotent_and_receipt_is_frozen(client, monkeypatch, isolated_backend):
    downloads, _ = isolated_backend
    plan = make_plan(client)
    payload = {"create_collection": True, "selected_item_ids": [plan["items"][0]["id"]]}
    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(lambda _: server.collections_service.commit(plan["id"], payload), range(12)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert len(server.pending_queue_jobs()) == 1
    assert len(server.collections_service.state["batches"]) == 1
    job = server.pending_queue_jobs()[0]
    assert job["collection_id"] == receipts[0]["collection"]["id"]
    assert job["batch_id"] == receipts[0]["batch"]["id"]
    assert job["target_relative_directory"].startswith("collections/summer-media--")
    finish_job(downloads, job)
    assert server.collections_service.get_batch(job["batch_id"])["progress"]["completed"] == 1
    expiry = server.collections_service.state["plans"][plan["id"]]["expires_at_epoch"]
    monkeypatch.setattr(backend.time, "time", lambda: expiry + 1)
    assert server.collections_service.commit(plan["id"], {"create_collection": True}) == receipts[0]


def test_reuse_preserves_root_file_and_membership_after_history_clear(client, isolated_backend):
    downloads, _ = isolated_backend
    path = downloads / "root.mp4"
    path.write_bytes(b"root-data")
    server.download_manager.download_history = [{
        "uuid": "root-media", "filename": "root.mp4", "url": "https://youtu.be/first",
        "resolution": "best", "status": "completed", "title": "Old title",
    }]
    server.download_manager.save_history()
    first = approve(client, make_plan(client))
    second = approve(client, make_plan(client, name="Another collection"))
    assert first["batch"]["progress"]["skipped"] == 1
    assert second["batch"]["progress"]["skipped"] == 1
    assert server.pending_queue_jobs() == []
    assert list(downloads.iterdir()) == [path]
    login(client)
    client.post("/youtube-dl/history/clear")
    for receipt in (first, second):
        detail = client.get(BASE + "/collections/" + receipt["collection"]["id"], headers=AUTH).json
        assert detail["items"][0]["relative_path"] == "root.mp4"
        assert detail["items"][0]["uuid"] == "root-media"
        assert detail["items"][0]["status"] == "completed"
        assert detail["collection"]["total_size_bytes"] == len(b"root-data")
    assert client.get("/static/preview/root-media").body == b"root-data"
    path.unlink()
    detail = client.get(BASE + "/collections/" + first["collection"]["id"], headers=AUTH).json
    assert detail["items"][0]["file_exists"] is False
    assert detail["items"][0]["status"] == "missing"
    assert detail["items"][0]["uuid"] == "root-media"
    assert detail["items"][0]["relative_path"] == "root.mp4"
    assert detail["collection"]["progress"]["missing"] == 1
    assert detail["batches"][0]["id"] == first["batch"]["id"]
    assert detail["batches"][0]["items"][0]["uuid"] == "root-media"
    assert detail["batches"][0]["items"][0]["relative_path"] == "root.mp4"
    assert detail["batches"][0]["items"][0]["status"] == "missing"


def test_normalized_matching_and_immutable_collection_directory(client):
    first = approve(client, make_plan(client, name="  Summer\n MEDIA  ", description=" Ｃurated   videos "))
    collection = first["collection"]
    plan = make_plan(client, name="summer media", description="Curated videos")
    assert plan["matching_collections"][0]["id"] == collection["id"]
    updated = client.patch_json(BASE + "/collections/" + collection["id"], {
        "name": "Renamed", "description": " New summary ",
    }, headers=AUTH).json["collection"]
    assert updated["relative_directory"] == collection["relative_directory"]
    assert updated["criteria"] == collection["criteria"]
    assert updated["name"] == "Renamed"
    assert client.patch_json(BASE + "/collections/" + collection["id"], {
        "criteria": {},
    }, headers=AUTH, status=400).json["code"] == "immutable_collection_fields"
    receipt = approve(client, plan, create_collection=False, collection_id=collection["id"])
    assert receipt["collection"]["id"] == collection["id"]
    assert len(server.pending_queue_jobs()) == 1


def test_existing_queue_attaches_to_multiple_collections_without_rerouting(client, isolated_backend):
    downloads, _ = isolated_backend
    queued = server.enqueue_download("https://youtu.be/first", "best", "web")
    first = approve(client, make_plan(client))
    second = approve(client, make_plan(client, name="Second collection"))
    jobs = server.pending_queue_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == queued["job"]["id"]
    assert jobs[0]["target_relative_directory"] == ""
    finish_job(downloads, jobs[0])
    for receipt in (first, second):
        detail = server.collections_service.get_collection(receipt["collection"]["id"])
        assert detail["collection"]["progress"]["completed"] == 1
        assert detail["items"][0]["relative_path"] == "video.mp4"
    assert not (downloads / "collections").exists()


def test_existing_job_changing_date_is_excluded_from_collection(client, isolated_backend):
    downloads, _ = isolated_backend
    server.enqueue_download("https://youtu.be/first", "best", "web")
    receipt = approve(client, make_plan(client))
    finish_job(downloads, server.pending_queue_jobs()[0], upload_date="1990-01-01")
    detail = server.collections_service.get_collection(receipt["collection"]["id"])
    assert detail["items"][0]["status"] == "skipped"
    assert detail["items"][0]["file_exists"] is False
    assert detail["items"][0]["failure_code"] == "outside_date_range"


def test_deleted_collection_does_not_reappear_when_active_job_finishes(client, isolated_backend):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    client.delete(BASE + "/collections/" + job["collection_id"], headers=AUTH)
    finish_job(downloads, job)
    assert server.collections_service.list_collections() == []
    assert server.collections_service.state["memberships"] == {}
    assert (downloads / job["target_relative_directory"] / "video.mp4").exists()
    assert server.collections_service.get_batch(receipt["batch"]["id"])["progress"]["completed"] == 1


def test_failed_history_membership_survives_clear_restart_and_retry(client, isolated_backend, monkeypatch):
    _, _state = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    server.download_manager.complete_download({
        "uuid": job["id"], "job_id": job["id"], "url": job["url"], "resolution": job["resolution"],
        "status": "failed", "failure_code": "network",
    })
    server.collections_service.reconcile()
    server.download_manager.clear_all_history()
    restart_backend(monkeypatch)
    detail = server.collections_service.get_collection(job["collection_id"])
    assert detail["collection"]["progress"]["failed"] == 1
    assert detail["items"][0]["failure_code"] == "network"
    assert server.pending_queue_jobs() == []
    login(client)
    retried = client.post("/youtube-dl/history/retry/" + job["id"]).json
    assert retried["queued"]
    retry_job = server.pending_queue_jobs()[0]
    assert retry_job["id"] != job["id"]
    assert retry_job["target_relative_directory"] == job["target_relative_directory"]
    assert retry_job["date_policy"] == job["date_policy"]
    assert server.collections_service.get_batch(receipt["batch"]["id"])["items"][0]["job_id"] == retry_job["id"]


@pytest.mark.parametrize("phase", ["before_queue", "after_queue", "after_final_state"])
def test_partial_commit_journal_recovers_without_duplicate_jobs(client, isolated_backend, monkeypatch, phase):
    plan = make_plan(client)
    original = server.apply_collection_queue_journal

    def interrupted(jobs, terminal=()):
        if phase != "before_queue":
            original(jobs, terminal)
        raise backend.StateError("simulated process interruption")

    if phase == "after_final_state":
        receipt = approve(client, plan)
    else:
        monkeypatch.setattr(server, "apply_collection_queue_journal", interrupted)
        result = client.post_json(BASE + f"/plans/{plan['id']}/commit", {
            "create_collection": True, "selected_item_ids": [plan["items"][0]["id"]],
        }, headers=AUTH, status=503)
        assert result.json["code"] == "state_unavailable"
        receipt = server.collections_service.state["plans"][plan["id"]]["commit_receipt"]
    reserved_id = receipt["batch"]["items"][0]["job_id"]
    monkeypatch.setattr(server, "apply_collection_queue_journal", original)
    service = restart_backend(monkeypatch)
    assert [job["id"] for job in server.pending_queue_jobs()] == [reserved_id]
    repeated = service.commit(plan["id"], {})
    assert repeated == receipt
    assert len(service.state["batches"]) == 1
    assert len(server.pending_queue_jobs()) == 1


def test_history_completion_reconciles_crash_before_collection_update(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    original = server.collections_service.observe_history
    monkeypatch.setattr(server.collections_service, "observe_history", MagicMock(side_effect=backend.StateError("interrupted")))
    with pytest.raises(backend.StateError):
        finish_job(downloads, job)
    monkeypatch.setattr(server.collections_service, "observe_history", original)
    service = restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    assert service.get_batch(receipt["batch"]["id"])["progress"]["completed"] == 1


def test_queue_removal_is_journaled_and_never_resurrected(client, monkeypatch):
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    server.remove_queued_job(job["id"])
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    assert server.collections_service.get_batch(job["batch_id"])["progress"]["failed"] == 1


@pytest.mark.parametrize("contents", ["{broken", '{"version":999}', '{"version":1,"collections":[]}'])
def test_corrupt_collections_fail_closed_without_overwriting(isolated_backend, contents):
    _, state = isolated_backend
    path = state / "bad-collections.json"
    path.write_text(contents)
    with pytest.raises(backend.StateError):
        backend.CollectionService(server.__dict__, str(path))
    assert path.read_text() == contents


def test_state_write_failure_is_reported_and_does_not_publish_preview(client, monkeypatch):
    monkeypatch.setattr(backend, "atomic_json_write", MagicMock(side_effect=OSError("private filesystem detail")))
    result = client.post_json(BASE + "/plans", {
        "name": "No persistence", "candidates": [{"url": "https://youtu.be/one"}],
    }, headers=AUTH, status=503).json
    assert result["code"] == "state_unavailable"
    assert "private filesystem detail" not in json.dumps(result)
    assert server.collections_service.state["plans"] == {}
    assert server.pending_queue_jobs() == []


def test_queue_write_failure_is_not_silently_accepted(client, monkeypatch):
    monkeypatch.setattr(server, "atomic_write_json", MagicMock(side_effect=OSError("disk full")))
    result = client.post_json(BASE + "/downloads", {"url": "https://youtu.be/one"}, headers=AUTH, status=503).json
    assert result["code"] == "state_unavailable"
    assert server.pending_queue_jobs() == []
    server.start_download_thread_if_needed.assert_not_called()


@pytest.mark.parametrize("relative", [
    "/etc/passwd", "../outside", "a/../outside", "./file.mp4", "a/./b.mp4", "a//b.mp4",
    "a\\..\\outside", "C:\\outside", "C:outside", "a/%2e%2e/outside", "a/%5coutside", "a/\x00bad",
])
def test_safe_paths_reject_traversal_instead_of_flattening(relative):
    assert server.safe_downfolder_path(relative) is None
    normalized = server.normalize_history_item({"uuid": "unsafe", "filename": relative})
    assert normalized["file_exists"] is False
    assert normalized["relative_path"] == ""


def test_nested_duplicate_basenames_are_distinct_for_scan_serving_and_delete(client, isolated_backend):
    downloads, _ = isolated_backend
    for directory, content in (("a", b"first"), ("b", b"second")):
        (downloads / directory).mkdir()
        (downloads / directory / "same.mp4").write_bytes(content)
        (downloads / directory / "same.jpg").write_bytes(content + b"-thumb")
    server.download_manager.download_history = [{
        "uuid": "first", "filename": "same.mp4", "relative_path": "a/same.mp4", "status": "completed",
    }]
    server.download_manager.save_history()
    items = server.download_manager.combined_history()
    assert {item["relative_path"] for item in items} == {"a/same.mp4", "b/same.mp4"}
    assert len({item["uuid"] for item in items}) == 2
    second_id = next(item["uuid"] for item in items if item["relative_path"] == "b/same.mp4")
    login(client)
    assert client.get("/static/preview/first").body == b"first"
    assert client.get("/static/preview/" + second_id).body == b"second"
    assert client.get("/static/thumbnail/" + second_id).body == b"second-thumb"
    ranged = client.get("/static/preview/" + second_id, headers={"Range": "bytes=1-3"}, status=206)
    assert ranged.body == b"eco"
    client.post("/youtube-dl/history/delete-file/first")
    assert not (downloads / "a/same.mp4").exists()
    assert not (downloads / "a/same.jpg").exists()
    assert (downloads / "b/same.mp4").read_bytes() == b"second"
    assert (downloads / "b/same.jpg").exists()


def test_history_migration_persists_relative_path(isolated_backend):
    _, state = isolated_backend
    (state / "history.json").write_text(json.dumps([{"uuid": "legacy", "filename": "root.mp4"}]))
    server.download_manager.load_history()
    assert server.download_manager.download_history[0]["relative_path"] == "root.mp4"
    assert json.loads((state / "history.json").read_text())[0]["relative_path"] == "root.mp4"


def test_symlink_files_directories_and_sidecars_are_never_followed(client, isolated_backend):
    downloads, state = isolated_backend
    outside = state / "outside.mp4"
    outside.write_bytes(b"private")
    (downloads / "link.mp4").symlink_to(outside)
    (downloads / "linked-directory").symlink_to(state, target_is_directory=True)
    (downloads / "real.mp4").write_bytes(b"safe")
    (downloads / "real.jpg").symlink_to(outside)
    (downloads / "inside-link").symlink_to(downloads, target_is_directory=True)
    assert server.safe_downfolder_path("link.mp4") is None
    assert server.safe_downfolder_path("linked-directory/outside.mp4") is None
    assert server.safe_downfolder_path("inside-link/real.mp4") is None
    assert [item["relative_path"] for item in server.list_mounted_file_items()] == ["real.mp4"]
    server.download_manager.download_history = [
        {"uuid": "link", "relative_path": "link.mp4"},
        {"uuid": "directory", "relative_path": "linked-directory/outside.mp4"},
        {"uuid": "safe", "relative_path": "real.mp4", "thumbnail_file": "real.jpg"},
    ]
    server.download_manager.save_history()
    login(client)
    for item_id in ("link", "directory"):
        client.get("/static/preview/" + item_id, status=404)
        client.get("/static/downfolder/" + item_id, status=404)
        client.post("/youtube-dl/history/delete-file/" + item_id, status=404)
    client.get("/static/thumbnail/safe", status=404)
    client.post("/youtube-dl/history/delete-file/safe")
    assert outside.read_bytes() == b"private"


@pytest.mark.parametrize("field", ["filepath", "physical_path", "relative_path", "target_relative_directory", "directory", "output"])
def test_callers_cannot_choose_physical_paths(client, monkeypatch, field):
    enqueue = MagicMock()
    fetch = MagicMock()
    monkeypatch.setattr(server, "enqueue_download", enqueue)
    monkeypatch.setattr(server, "fetch_media_metadata", fetch)
    result = client.post_json(BASE + "/downloads", {
        "url": "https://youtu.be/one", field: "/private/escape",
    }, headers=AUTH, status=400).json
    assert result["code"] == "caller_path_forbidden"
    result = client.post_json(BASE + "/plans", {
        "name": "Unsafe", "candidates": [{"url": "https://youtu.be/one", field: "../escape"}],
    }, headers=AUTH, status=400).json
    assert result["code"] == "caller_path_forbidden"
    client.post_json("/youtube-dl/rest", {
        "url": "https://youtu.be/one", "resolution": "best", field: "/escape",
    }, headers=AUTH, status=400)
    login(client)
    client.post_json("/youtube-dl/q", {
        "url": "https://youtu.be/one", "resolution": "best", field: "/escape",
    }, status=400)
    enqueue.assert_not_called()
    fetch.assert_not_called()


@pytest.mark.parametrize("metadata, expected", [
    ({"id": "one", "title": "Moved date", "upload_date": "19900101"}, "outside_date_range"),
    ({"id": "one", "title": "No date"}, "date_unknown"),
    ({}, "metadata_unavailable"),
    ({"_type": "playlist", "entries": []}, "metadata_unavailable"),
])
def test_date_preflight_blocks_transfer_after_metadata_change(client, monkeypatch, isolated_backend, metadata, expected):
    downloads, _ = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    popen = MagicMock()
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: metadata)
    monkeypatch.setattr(server.subprocess, "Popen", popen)
    server.download(job)
    popen.assert_not_called()
    assert not (downloads / "collections").exists()
    batch = server.collections_service.get_batch(job["batch_id"])
    assert batch["items"][0]["status"] == "skipped"
    assert batch["items"][0]["failure_code"] == expected


@pytest.mark.parametrize("allow_unknown", [False, True])
def test_transfer_enforces_date_policy_with_ytdlp_filters(client, allow_unknown):
    from yt_dlp.utils import match_filter_func

    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    job["date_policy"]["include_unknown_date"] = allow_unknown
    command = server.build_youtube_dl_cmd(job)
    expression = command[command.index("--match-filter") + 1]
    match = match_filter_func([expression])
    assert match({"upload_date": "20260810"}, incomplete=False) is None
    assert match({"upload_date": "19900101"}, incomplete=False) is not None
    assert (match({}, incomplete=False) is None) == allow_unknown
    assert command[command.index("--dateafter") + 1] == "20260801"
    assert command[command.index("--datebefore") + 1] == "20260831"
    assert "home:" + os.path.join(server.DOWNFOLDER_DIR, job["target_relative_directory"]) in command
    assert "--no-playlist" in command


def test_collection_output_markers_must_stay_in_derived_directory(client, isolated_backend):
    downloads, state = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    for path in (state / "outside.mp4", downloads / "root.mp4"):
        path.write_bytes(b"data")
        with pytest.raises(backend.APIError, match="unsafe_path"):
            server.build_completed_history_item(job, {"filepath": str(path)}, {})


def test_transfer_refuses_preexisting_symlinks(client, isolated_backend):
    downloads, state = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    directory = downloads / job["target_relative_directory"]
    directory.mkdir(parents=True)
    (directory / "video.mp4").symlink_to(state / "outside.mp4")
    with pytest.raises(backend.APIError, match="unsafe_path"):
        server.prepare_transfer_directory(job)


def test_connection_tokens_are_one_time_redacted_restrictive_and_revocable(client, isolated_backend, capsys):
    _, state = isolated_backend
    client.get(BASE + "/connections", headers=AUTH, status=401)
    login(client)
    created = client.post_json(BASE + "/connections", {"name": "Desktop MCP"}).json
    token = created["token"]
    connection = created["connection"]
    assert token.startswith("ydlnas_")
    assert "token_hash" not in connection
    contents = (state / "connections.json").read_text()
    assert token not in contents
    assert "token_hash" in contents
    assert stat.S_IMODE((state / "connections.json").stat().st_mode) == 0o600
    listed = client.get(BASE + "/connections")
    assert listed.headers["Cache-Control"] == "no-store"
    assert token not in listed.text and "token_hash" not in listed.text
    token_client = TestApp(default_app())
    token_auth = {"Authorization": "Bearer " + token}
    assert token_client.get(BASE + "/mcp/auth", headers=token_auth).json == {"authenticated": True}
    assert token_client.get(BASE + "/library", headers=token_auth).json["items"] == []
    assert client.get(BASE + "/connections").json["connections"][0]["last_used_at"]
    client.delete(BASE + "/connections/" + connection["id"])
    token_client.get(BASE + "/mcp/auth", headers=token_auth, status=401)
    token_client.get(BASE + "/library", headers=token_auth, status=401)
    assert token not in capsys.readouterr().out


def test_mcp_auth_is_bearer_only_and_tokens_do_not_grant_legacy_privileges(client):
    login(client)
    token = client.post_json(BASE + "/connections", {"name": "Tool"}).json["token"]
    client.get(BASE + "/mcp/auth", status=401)
    assert client.get(BASE + "/mcp/auth", headers=AUTH).json == {"authenticated": True}
    unauthenticated = TestApp(default_app())
    token_auth = {"Authorization": "Bearer " + token}
    unauthenticated.get(BASE + "/connections", headers=token_auth, status=401)
    unauthenticated.post_json(BASE + "/connections", {"name": "Escalate"}, headers=token_auth, status=401)
    unauthenticated.get("/youtube-dl/cookies", headers=token_auth, status=403)
    unauthenticated.post("/youtube-dl/history/delete-file/anything", headers=token_auth, status=403)
    unauthenticated.get("/static/preview/anything", headers=token_auth, status=403)
    unauthenticated.post_json("/youtube-dl/rest", {
        "url": "https://youtu.be/one", "resolution": "best",
    }, headers=token_auth, status=403)
    unauthenticated.get(BASE + "/mcp/auth?token=" + token, status=401)
    assert "next=" in unauthenticated.get("/youtube-dl/ai-connect", headers=token_auth, status=302).location


def test_connection_browser_mutations_reject_cross_origin(client):
    login(client)
    for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Origin": "null"}):
        response = client.post_json(BASE + "/connections", {"name": "Bad origin"}, headers=headers, status=403)
        assert response.json["code"] == "cross_origin_request"
    result = client.post_json(BASE + "/connections", {"name": "Same origin"}, headers={"Origin": "http://localhost"})
    assert result.json["token"]


def test_mcp_auth_without_bearer_is_json_401_even_without_dashboard_credentials(client, monkeypatch):
    monkeypatch.setenv("MY_ID", "")
    monkeypatch.setenv("MY_PW", "")
    dashboard_auth = MagicMock(side_effect=AssertionError("MCP readiness must not initialize dashboard authentication"))
    monkeypatch.setattr(server, "load_auth_data", dashboard_auth)
    result = client.get(BASE + "/mcp/auth", status=401)
    assert result.content_type == "application/json"
    assert result.json == {"success": False, "code": "unauthorized", "msg": "unauthorized"}
    assert result.headers["Cache-Control"] == "no-store"
    dashboard_auth.assert_not_called()


@pytest.mark.parametrize("path, page, collection_id", [
    ("/youtube-dl", "downloads", ""),
    ("/youtube-dl/collections", "collections", ""),
    ("/youtube-dl/collections/example-id", "collections", "example-id"),
    ("/youtube-dl/ai-connect", "ai-connect", ""),
])
def test_dashboard_page_context_is_shared(client, monkeypatch, path, page, collection_id):
    login(client)
    render = MagicMock(return_value="dashboard")
    monkeypatch.setattr(server, "render_localized_template", render)
    client.get(path)
    assert render.call_args.args[0] == "./static/template/index.tpl"
    context = render.call_args.kwargs
    assert context["page"] == page
    assert context["collection_id"] == collection_id
    assert context["locale_next"] == path
    assert context["shared_url_json"] == '""'


def test_collection_page_preserves_next_through_login_and_terms(client, monkeypatch):
    path = "/youtube-dl/collections/example"
    response = client.get(path, status=302)
    assert "next=%2Fyoutube-dl%2Fcollections%2Fexample" in response.location
    data = server.load_auth_data()
    monkeypatch.setattr(server, "load_auth_data", lambda: {**data, "TERMS_ACCEPTED": "N"})
    response = client.get(path, status=302)
    assert "/terms?next=%2Fyoutube-dl%2Fcollections%2Fexample" in response.location


def test_download_item_deep_link_survives_login_terms_and_locale_context(client, monkeypatch):
    path = "/youtube-dl?item=media-uuid"
    response = client.get(path, status=302)
    assert "next=%2Fyoutube-dl%3Fitem%3Dmedia-uuid" in response.location
    response = client.post("/login", {"id": "tester", "myPw": "secret", "next": path}, status=302)
    assert response.location.endswith(path)
    render = MagicMock(return_value="dashboard")
    monkeypatch.setattr(server, "render_localized_template", render)
    client.get(path)
    assert render.call_args.kwargs["locale_next"] == path
    data = server.load_auth_data()
    monkeypatch.setattr(server, "load_auth_data", lambda: {**data, "TERMS_ACCEPTED": "N"})
    response = client.get(path, status=302)
    assert "/terms?next=%2Fyoutube-dl%3Fitem%3Dmedia-uuid" in response.location


def test_run_server_accepts_loopback_overrides_and_keeps_direct_port(monkeypatch):
    run = MagicMock()
    monkeypatch.setattr(server, "run", run)
    monkeypatch.setattr(server, "load_persisted_queue", lambda: 0)
    monkeypatch.setattr(server, "port", 8080)
    monkeypatch.setenv("YDLNAS_WEB_HOST", "127.0.0.1")
    monkeypatch.setenv("YDLNAS_WEB_PORT", "8081")
    monkeypatch.setenv("APP_PORT", "8099")
    server.run_server()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8081
    monkeypatch.delenv("YDLNAS_WEB_HOST")
    monkeypatch.delenv("YDLNAS_WEB_PORT")
    server.run_server()
    assert run.call_args.kwargs["host"] == "0.0.0.0"
    assert str(run.call_args.kwargs["port"]) == "8099"


def test_different_batches_keep_independent_date_policies_for_shared_membership(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {"id": "first", "title": "Unknown date"})
    first_plan = make_plan(client)
    first = approve(client, first_plan, include_unknown_dates=[first_plan["items"][0]["id"]])
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "id": "first", "title": "Now dated", "upload_date": "20260810",
    })
    second_plan = make_plan(client)
    second = approve(client, second_plan, create_collection=False, collection_id=first["collection"]["id"])
    assert len(server.collections_service.state["memberships"]) == 1
    assert len(server.pending_queue_jobs()) == 1
    finish_job(downloads, server.pending_queue_jobs()[0], upload_date=None)
    assert server.collections_service.get_batch(first["batch"]["id"])["progress"]["completed"] == 1
    assert server.collections_service.get_batch(second["batch"]["id"])["progress"]["skipped"] == 1
    assert server.collections_service.get_collection(first["collection"]["id"])["collection"]["progress"]["completed"] == 1


def test_metadata_unknown_at_transfer_does_not_reuse_preflight_date(client, isolated_backend):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    target = downloads / job["target_relative_directory"] / "media.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"media")
    item = server.build_completed_history_item(
        job, {"filepath": str(target), "upload_date": ""}, {"upload_date": "2026-08-10"},
    )
    assert item["upload_date"] is None
    server.download_manager.complete_download(item)
    assert server.collections_service.get_batch(receipt["batch"]["id"])["progress"]["skipped"] == 1


def test_date_filter_cannot_be_bypassed_by_additional_admin_filter(client, monkeypatch):
    from yt_dlp import parse_options

    approve(client, make_plan(client))
    monkeypatch.setattr(server, "YTDLP_EXTRA_ARGS", "--match-filter duration>0")
    command = server.build_youtube_dl_cmd(server.pending_queue_jobs()[0])
    options = parse_options(["--ignore-config"] + command[1:]).ydl_opts
    assert options["match_filter"]({"duration": 100, "upload_date": "19900101"}, incomplete=False) is not None
    assert options["match_filter"]({"duration": 100, "upload_date": "20260801"}, incomplete=False) is None


def test_preview_cli_is_simulation_only_and_ignores_side_effect_options(monkeypatch, isolated_backend):
    from yt_dlp import parse_options

    downloads, _ = isolated_backend
    process = MagicMock()
    process.returncode = 0
    process.communicate.return_value = ('{"id":"one","title":"Verified"}', None)
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(server.subprocess, "Popen", popen)
    monkeypatch.setattr(server, "YTDLP_EXTRA_ARGS", "--write-thumbnail --exec before_dl:unsafe-command")
    result = REAL_FETCH_MEDIA_METADATA("https://youtu.be/one", direct=True)
    assert result["id"] == "one"
    command = popen.call_args.args[0]
    options = parse_options(command[1:]).ydl_opts
    assert options["simulate"] is True
    assert "--exec" not in command
    assert "--write-thumbnail" not in command
    assert "--no-playlist" in command
    assert not list(downloads.iterdir())


def test_completed_collection_download_uses_safe_target_and_persists_membership(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    captured = []

    def transfer(command, **kwargs):
        captured.append(command)
        target = downloads / job["target_relative_directory"] / "downloaded.mp4"
        target.write_bytes(b"download-data")
        output = {"filepath": str(target), "id": "first", "title": "Finished", "upload_date": "20260810"}
        process = MagicMock()
        process.stdout = io.StringIO(server.YTDLP_ITEM_PREFIX + json.dumps(output) + "\n")
        process.poll.return_value = 0
        return process

    monkeypatch.setattr(server.subprocess, "Popen", transfer)
    server.download(job)
    assert len(captured) == 1
    detail = server.collections_service.get_collection(receipt["collection"]["id"])
    item = detail["items"][0]
    assert item["relative_path"] == job["target_relative_directory"] + "/downloaded.mp4"
    assert item["status"] == "completed"
    assert item["uuid"] == job["id"]
    assert item["file_size_bytes"] == len(b"download-data")
    saved = json.loads(Path(server.download_manager.history_file).read_text())
    assert saved[0]["relative_path"] == item["relative_path"]
    assert saved[0]["job_id"] == job["id"]
    assert saved[0]["batch_id"] == job["batch_id"]
    assert server.pending_queue_jobs() == []


def test_interruption_after_queue_disk_write_before_publication_recovers(client, monkeypatch):
    plan = make_plan(client)
    original = server.write_queue_snapshot

    def fail_after_disk(active, pending):
        original(active, pending)
        raise backend.StateError("interrupted before queue publication")

    monkeypatch.setattr(server, "write_queue_snapshot", fail_after_disk)
    client.post_json(BASE + f"/plans/{plan['id']}/commit", {
        "create_collection": True, "selected_item_ids": [plan["items"][0]["id"]],
    }, headers=AUTH, status=503)
    assert server.pending_queue_jobs() == []
    persisted = json.loads(Path(server.QUEUE_STATE_FILE).read_text())
    expected_job = persisted["pending"][0]["id"]
    monkeypatch.setattr(server, "write_queue_snapshot", original)
    restart_backend(monkeypatch)
    assert [job["id"] for job in server.pending_queue_jobs()] == [expected_job]


def test_queue_restore_rejects_corruption_instead_of_dropping_work(isolated_backend):
    _, state = isolated_backend
    path = state / "queue.json"
    path.write_text('{"version":5,"pending":[{"url":"file:///private/escape","resolution":"best"}]}')
    with pytest.raises(backend.StateError):
        server.load_persisted_queue()
    assert not server.queue_state_loaded
    assert server.pending_queue_jobs() == []


def test_new_symlink_at_collection_directory_fails_job_without_following_it(client, isolated_backend, monkeypatch):
    downloads, state = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    target = downloads / job["target_relative_directory"]
    target.parent.mkdir()
    target.symlink_to(state, target_is_directory=True)
    restart_backend(monkeypatch)
    popen = MagicMock()
    monkeypatch.setattr(server.subprocess, "Popen", popen)
    server.download(server.pending_queue_jobs()[0])
    popen.assert_not_called()
    assert server.collections_service.get_batch(job["batch_id"])["progress"]["failed"] == 1
    assert not (state / "downloaded.mp4").exists()


def test_scoped_retry_attaches_to_existing_queued_retry(client, isolated_backend):
    _, _state = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    server.download_manager.complete_download({
        "uuid": job["id"], "url": job["url"], "resolution": job["resolution"], "status": "failed",
    })
    server.collections_service.reconcile()
    replacement = server.enqueue_download(job["url"], job["resolution"], "web")["job"]
    login(client)
    retried = client.post("/youtube-dl/history/retry/" + job["id"]).json
    assert retried["duplicate_type"] == "queue"
    batch = server.collections_service.get_batch(job["batch_id"])
    assert batch["items"][0]["job_id"] == replacement["id"]
    assert batch["progress"]["queued"] == 1
    assert len(server.pending_queue_jobs()) == 1


def test_existing_file_retry_is_preflighted_again_under_saved_date_policy(client, isolated_backend):
    downloads, _ = isolated_backend
    approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    server.download_manager.complete_download({
        "uuid": job["id"], "url": job["url"], "resolution": job["resolution"], "status": "failed",
    })
    server.collections_service.reconcile()
    root_job = server.create_queue_job(job["url"], "best", "web")
    finish_job(downloads, root_job, name="root.mp4")
    login(client)
    retried = client.post("/youtube-dl/history/retry/" + job["id"]).json
    assert retried["queued"] is True
    assert server.pending_queue_jobs()[0]["date_policy"] == job["date_policy"]


def test_metadata_identity_matches_existing_active_job_for_alias_url(client):
    job = server.create_queue_job("https://www.youtube.com/watch?v=first", "best", "web")
    job.update(media_id="first", extractor="Youtube", state="downloading")
    server.set_active_queue_job(job)
    plan = make_plan(client)
    assert plan["items"][0]["status"] == "already_queued"
    result = approve(client, plan)
    assert result["batch"]["items"][0]["job_id"] == job["id"]
    assert result["batch"]["progress"]["running"] == 1
    assert server.pending_queue_jobs() == []


def test_clear_history_never_erases_unsaved_collection_completion(client, monkeypatch):
    approve(client, make_plan(client))
    server.download_manager.download_history = [{"uuid": "keep", "status": "failed"}]
    monkeypatch.setattr(server.collections_service, "observe_history", MagicMock(side_effect=backend.StateError("cannot preserve")))
    with pytest.raises(backend.StateError):
        server.download_manager.clear_all_history()
    assert server.download_manager.download_history[0]["uuid"] == "keep"


def test_collection_deletion_is_metadata_only_for_completed_media(client, isolated_backend):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    item = finish_job(downloads, job)
    path = downloads / item["relative_path"]
    client.delete(BASE + "/collections/" + receipt["collection"]["id"], headers=AUTH)
    assert path.read_bytes() == b"media"
    assert path.parent.is_dir()
    assert server.download_manager.get_history_item(item["uuid"])
    client.get(BASE + "/collections/" + receipt["collection"]["id"], headers=AUTH, status=404)


def test_library_reports_external_removal_as_missing(client, isolated_backend):
    downloads, _ = isolated_backend
    job = server.create_queue_job("https://youtu.be/root", "best", "web")
    item = finish_job(downloads, job)
    (downloads / item["relative_path"]).unlink()
    library = client.get(BASE + "/library", headers=AUTH).json["items"]
    assert library[0]["status"] == "missing"
    assert library[0]["file_exists"] is False


def test_connection_auth_survives_reload_and_diagnostics_redact_bearer(client):
    login(client)
    token = client.post_json(BASE + "/connections", {"name": "Persisted"}).json["token"]
    reloaded = backend.ConnectionStore(server.CONNECTIONS_STATE_FILE)
    assert reloaded.validate(token)
    assert not reloaded.validate("invalid")
    diagnostic = server.sanitize_diagnostic_text(f"Authorization: Bearer {token}; raw={token} api=integration-token")
    assert token not in diagnostic
    assert "integration-token" not in diagnostic


@pytest.mark.parametrize("payload", [
    {"collection_id": {"id": "invalid"}},
    {"create_collection": "true"},
    {"create_collection": True, "collection_id": "not-both"},
])
def test_malformed_commit_destination_is_a_client_error(client, payload):
    plan = make_plan(client)
    result = client.post_json(BASE + f"/plans/{plan['id']}/commit", {
        **payload, "selected_item_ids": [plan["items"][0]["id"]],
    }, headers=AUTH, status=400)
    assert result.json["code"] in {"invalid_commit", "collection_selection_required"}


def test_running_service_does_not_overwrite_changed_or_corrupt_collection_state(client, isolated_backend):
    _, state = isolated_backend
    make_plan(client)
    path = state / "collections.json"
    path.write_text("{unexpected corruption")
    assert client.get(BASE + "/collections", headers=AUTH, status=503).json["code"] == "state_unavailable"
    client.post_json(BASE + "/plans", {
        "name": "Must not reset", "candidates": [{"url": "https://youtu.be/one"}],
    }, headers=AUTH, status=503)
    assert path.read_text() == "{unexpected corruption"


def test_failed_queue_restore_does_not_publish_or_duplicate_jobs(isolated_backend, monkeypatch):
    _, state = isolated_backend
    job = server.create_queue_job("https://youtu.be/one", "best", "web")
    (state / "queue.json").write_text(json.dumps({"version": 5, "active": None, "pending": [job]}))
    original = server.write_queue_snapshot
    monkeypatch.setattr(server, "write_queue_snapshot", MagicMock(side_effect=backend.StateError("write failed")))
    with pytest.raises(backend.StateError):
        server.load_persisted_queue()
    assert server.pending_queue_jobs() == []
    assert not server.queue_state_loaded
    monkeypatch.setattr(server, "write_queue_snapshot", original)
    server.load_persisted_queue()
    assert [restored["id"] for restored in server.pending_queue_jobs()] == [job["id"]]


@pytest.mark.parametrize("payload", [
    {"version": 5, "active": {}, "pending": []},
    {"version": 5, "active": None, "pending": "broken"},
])
def test_malformed_queue_tables_fail_closed(isolated_backend, payload):
    _, state = isolated_backend
    (state / "queue.json").write_text(json.dumps(payload))
    with pytest.raises(backend.StateError):
        server.load_persisted_queue()
    assert server.pending_queue_jobs() == []


def test_history_never_merges_identical_basenames_in_different_directories(isolated_backend):
    downloads, _ = isolated_backend
    for prefix in ("first", "second"):
        path = downloads / prefix / "video.mp4"
        path.parent.mkdir()
        path.write_bytes(prefix.encode())
        server.download_manager.complete_download({
            "uuid": prefix, "relative_path": prefix + "/video.mp4", "filename": "video.mp4",
            "resolution": "best", "media_id": "same-id", "extractor": "Youtube", "status": "completed",
        })
    assert len(server.download_manager.download_history) == 2
    assert {item["relative_path"] for item in server.download_manager.download_history} == {
        "first/video.mp4", "second/video.mp4",
    }


def test_persisted_queue_rejects_caller_shaped_targets():
    job = server.create_queue_job("https://youtu.be/one", "best", "web")
    for target in ("../outside", "/absolute", "collections/arbitrary", "collections/a--123456789abc"):
        assert server.normalize_queue_job({
            **job, "target_relative_directory": target,
            "collection_id": "not-a-uuid", "batch_id": "batch", "date_policy": {},
        }) is None


def test_file_discovered_at_preflight_is_reused_and_retains_verified_date(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    receipt = approve(client, make_plan(client))
    job = server.pending_queue_jobs()[0]
    (downloads / "arrived.mp4").write_bytes(b"existing")
    server.download_manager.download_history = [{
        "uuid": "arrived", "filename": "arrived.mp4", "url": job["url"],
        "resolution": "best", "status": "completed",
    }]
    server.download_manager.save_history()
    popen = MagicMock()
    monkeypatch.setattr(server.subprocess, "Popen", popen)
    server.download(job)
    popen.assert_not_called()
    batch = server.collections_service.get_batch(receipt["batch"]["id"])
    assert batch["items"][0]["uuid"] == "arrived"
    assert batch["progress"]["skipped"] == 1
    detail = server.collections_service.get_collection(job["collection_id"])
    assert detail["items"][0]["status"] == "completed"
    assert detail["items"][0]["upload_date"] == "2026-08-10"
    server.download_manager.clear_all_history()
    assert server.collections_service.get_collection(job["collection_id"])["items"][0]["status"] == "completed"
    assert not (downloads / "collections").exists()


def test_appended_batch_exposes_its_own_criteria_and_normalized_file_properties(client, isolated_backend, monkeypatch):
    downloads, state = isolated_backend
    august = {"date_from": "2026-08-01", "date_to": "2026-08-31"}
    september = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
    monkeypatch.setattr(server, "fetch_media_metadata", lambda url, **kwargs: {
        "id": url.rsplit("/", 1)[-1], "title": "Verified", "extractor_key": "Youtube",
        "upload_date": "20260910" if url.endswith("second") else "20260810",
    })
    first_plan = make_plan(client, criteria=august)
    first = approve(client, first_plan)
    second_plan = make_plan(client, [{"url": "https://youtu.be/second"}], criteria=september)
    second = approve(client, second_plan, create_collection=False, collection_id=first["collection"]["id"])
    assert first["batch"]["criteria"] == august
    assert second["batch"]["criteria"] == september
    assert second["collection"]["criteria"] == august
    assert json.loads((state / "collections.json").read_text())["batches"][second["batch"]["id"]]["criteria"] == september
    assert server.collections_service.commit(second_plan["id"], {}) == second

    jobs = {job["batch_id"]: job for job in server.pending_queue_jobs()}
    finish_job(downloads, jobs[first["batch"]["id"]], name="august.mp4")
    completed = finish_job(downloads, jobs[second["batch"]["id"]], name="september.mp4", upload_date="2026-09-10")
    detail = client.get(BASE + "/collections/" + first["collection"]["id"], headers=AUTH).json
    assert {batch["id"]: batch["criteria"] for batch in detail["batches"]} == {
        first["batch"]["id"]: august, second["batch"]["id"]: september,
    }
    batch = client.get(BASE + "/batches/" + second["batch"]["id"], headers=AUTH).json["batch"]
    assert batch["criteria"] == september
    assert {key: batch["items"][0][key] for key in ("uuid", "file_exists", "file_size_bytes", "relative_path", "status")} == {
        "uuid": completed["uuid"], "file_exists": True, "file_size_bytes": len(b"media"),
        "relative_path": completed["relative_path"], "status": "completed",
    }
    (downloads / completed["relative_path"]).unlink()
    missing = client.get(BASE + "/batches/" + second["batch"]["id"], headers=AUTH).json["batch"]["items"][0]
    assert missing["uuid"] == completed["uuid"]
    assert missing["relative_path"] == completed["relative_path"]
    assert missing["status"] == "missing"
    assert missing["file_exists"] is False
    assert missing["file_size_bytes"] == 0
    assert server.collections_service.commit(second_plan["id"], {}) == second


def test_legacy_batch_criteria_are_derived_from_approved_plan_without_changing_receipt(client, monkeypatch):
    plan = make_plan(client, criteria={})
    original = approve(client, plan)
    state = copy.deepcopy(server.collections_service.state)
    batch_id = original["batch"]["id"]
    del state["batches"][batch_id]["criteria"]
    del state["plans"][plan["id"]]["commit_receipt"]["batch"]["criteria"]
    server.collections_service._save(state)
    service = backend.CollectionService(server.__dict__, server.COLLECTIONS_STATE_FILE)
    monkeypatch.setattr(server, "collections_service", service)
    assert service.get_batch(batch_id)["criteria"] == {"date_from": None, "date_to": None}
    assert service.get_collection(original["collection"]["id"])["batches"][0]["criteria"] == plan["criteria"]
    assert service.commit(plan["id"], {}) == original
    assert service.commit(plan["id"], {}) == original


def test_batch_criteria_cannot_disagree_with_approved_plan(client, isolated_backend):
    _, state_directory = isolated_backend
    receipt = approve(client, make_plan(client))
    state = copy.deepcopy(server.collections_service.state)
    state["batches"][receipt["batch"]["id"]]["criteria"] = {"date_from": None, "date_to": None}
    path = state_directory / "mismatched-criteria.json"
    path.write_text(json.dumps(state))
    with pytest.raises(backend.StateError, match="Batch criteria"):
        backend.CollectionService(server.__dict__, str(path))


def test_gevent_preview_holds_no_state_locks_and_commit_is_fast(client, live_gevent_server, monkeypatch):
    port = live_gevent_server["port"]
    plan = make_plan(client)
    token = server.connections_store.create("Responsiveness probe")["token"]
    metadata_started = Event()
    release_metadata = Event()

    def slow_metadata(url, *args, **kwargs):
        assert url.endswith("/blocked"), "Commit must not perform network metadata work"
        metadata_started.set()
        assert release_metadata.wait(timeout=10)
        return {"id": "blocked", "title": "Verified slow metadata", "extractor_key": "Youtube", "upload_date": "20260810"}

    monkeypatch.setattr(server, "fetch_media_metadata", slow_metadata)
    with ThreadPoolExecutor(max_workers=1) as requests:
        slow_request = requests.submit(
            loopback_json, port, BASE + "/plans",
            {"name": "Slow preview", "candidates": [{"url": "https://youtu.be/blocked"}]}, AUTH, 8,
        )
        try:
            assert metadata_started.wait(timeout=3)
            for lock in (server.collections_service.lock, server.queue_operation_lock, server.connections_store.lock):
                assert lock.acquire(blocking=False), "Preview held a state lock during network work"
                lock.release()
            started = time.monotonic()
            status, committed = loopback_json(port, BASE + f"/plans/{plan['id']}/commit", {
                "create_collection": True, "selected_item_ids": [plan["items"][0]["id"]],
            }, AUTH)
            assert status == 200 and committed["batch"]["id"]
            assert time.monotonic() - started < 1
            assert loopback_json(port, BASE + "/collections/" + committed["collection"]["id"], headers=AUTH)[0] == 200
            assert loopback_json(port, "/youtube-dl/rest", {
                "url": "https://youtu.be/another", "resolution": "best",
            }, AUTH)[0] == 200
            started = time.monotonic()
            assert loopback_json(port, "/health")[0] == 200
            assert loopback_json(port, BASE + "/mcp/auth", headers={"Authorization": "Bearer " + token}) == (
                200, {"authenticated": True},
            )
            # A concurrent 401 must not overwrite the slow request's response context.
            assert loopback_json(port, BASE + "/mcp/auth")[0] == 401
            assert time.monotonic() - started < 1
            assert not slow_request.done()
        finally:
            release_metadata.set()
        status, result = slow_request.result(timeout=4)
        assert status == 200
        assert "plan" in result


def test_gevent_preflight_revalidates_dates_without_holding_state_locks(client, live_gevent_server, monkeypatch):
    port = live_gevent_server["port"]
    receipt = approve(client, make_plan(client))
    token = server.connections_store.create("Preflight readiness")["token"]
    metadata_started = Event()
    release_metadata = Event()

    def changed_metadata(*args, **kwargs):
        metadata_started.set()
        assert release_metadata.wait(timeout=10)
        return {"id": "first", "title": "Date changed after approval", "upload_date": "19900101"}

    monkeypatch.setattr(server, "fetch_media_metadata", changed_metadata)
    transfer = MagicMock(side_effect=AssertionError("Out-of-range media must not transfer"))
    monkeypatch.setattr(server.subprocess, "Popen", transfer)
    with ThreadPoolExecutor(max_workers=1) as workers:
        worker = workers.submit(server.dl_worker)
        try:
            assert metadata_started.wait(timeout=3)
            for lock in (server.collections_service.lock, server.queue_operation_lock, server.connections_store.lock):
                assert lock.acquire(blocking=False), "Preflight held a state lock during network work"
                lock.release()
            started = time.monotonic()
            assert loopback_json(port, "/health")[0] == 200
            assert loopback_json(port, BASE + "/mcp/auth", headers={"Authorization": "Bearer " + token})[0] == 200
            assert loopback_json(port, BASE + "/mcp/auth")[0] == 401
            status, live = loopback_json(port, BASE + "/batches/" + receipt["batch"]["id"], headers=AUTH)
            assert status == 200 and live["batch"]["progress"]["running"] == 1
            assert time.monotonic() - started < 1
        finally:
            release_metadata.set()
            server.dl_q.put(None)
        worker.result(timeout=4)
    batch = server.collections_service.get_batch(receipt["batch"]["id"])
    assert batch["progress"]["skipped"] == 1
    assert batch["items"][0]["failure_code"] == "outside_date_range"
    transfer.assert_not_called()


def test_native_backend_notifications_are_sent_on_the_websocket_hub(client, live_gevent_server, monkeypatch):
    from geventwebsocket.websocket import WebSocket

    sent_on_threads = []
    original_send = WebSocket.send

    def tracked_send(self, *args, **kwargs):
        sent_on_threads.append(get_ident())
        return original_send(self, *args, **kwargs)

    monkeypatch.setattr(WebSocket, "send", tracked_send)
    login(client)
    port = live_gevent_server["port"]
    connection = socket.create_connection(("127.0.0.1", port), timeout=2)
    stream = connection.makefile("rb")
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        connection.sendall((
            f"GET /websocket HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\nCookie: account={client.cookies['account']}\r\n\r\n"
        ).encode("ascii"))
        assert b"101" in stream.readline()
        while stream.readline() != b"\r\n":
            pass

        def frame():
            header = stream.read(2)
            assert len(header) == 2
            size = header[1] & 127
            if size == 126:
                size = int.from_bytes(stream.read(2), "big")
            elif size == 127:
                size = int.from_bytes(stream.read(8), "big")
            return stream.read(size).decode("utf-8")

        assert "[HISTORY_RESTORE_COMPLETE]" in frame()
        status, result = loopback_json(
            port, BASE + "/downloads", {"url": "https://youtu.be/first", "resolution": "best"}, AUTH,
        )
        assert status == 200 and result["queued"]
        assert "[QUEUE_UPDATED]" in frame()
        assert set(sent_on_threads) == {live_gevent_server["thread"].ident}
    finally:
        stream.close()
        connection.close()
    deadline = time.monotonic() + 2
    while server.download_manager.connected_clients and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not server.download_manager.connected_clients


class TrackedLock:
    def __init__(self, lock, entered):
        self.lock = lock
        self.entered = entered

    def acquire(self, *args, **kwargs):
        self.entered.set()
        return self.lock.acquire(*args, **kwargs)

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_args):
        self.release()


@pytest.mark.parametrize("lock_name", ["collections", "queue_operation", "queue_state"])
def test_gevent_state_lock_waiters_cannot_starve_health_or_auth(live_gevent_server, monkeypatch, lock_name):
    port, hub = live_gevent_server["port"], live_gevent_server["hub"]
    token = server.connections_store.create("Lock contention probe")["token"]
    configured = Event()

    def constrain_pool():
        hub.threadpool.maxsize = 1
        configured.set()

    hub.loop.run_callback_threadsafe(constrain_pool)
    assert configured.wait(timeout=3)
    entered = Event()
    if lock_name == "collections":
        lock = server.collections_service.lock
        monkeypatch.setattr(server.collections_service, "lock", TrackedLock(lock, entered))
        path = BASE + "/collections"
    else:
        attribute = lock_name + "_lock"
        lock = getattr(server, attribute)
        monkeypatch.setattr(server, attribute, TrackedLock(lock, entered))
        path = BASE + ("/downloads" if lock_name == "queue_state" else "/collections")
    with ThreadPoolExecutor(max_workers=1) as requests:
        lock.acquire()
        stalled = requests.submit(loopback_json, port, path, None, AUTH, 8)
        try:
            assert entered.wait(timeout=3)
            assert not stalled.done()
            started = time.monotonic()
            assert loopback_json(port, "/health")[0] == 200
            assert loopback_json(port, BASE + "/mcp/auth", headers={"Authorization": "Bearer " + token}) == (
                200, {"authenticated": True},
            )
            assert loopback_json(port, BASE + "/mcp/auth")[0] == 401
            assert time.monotonic() - started < 1
        finally:
            lock.release()
        assert stalled.result(timeout=4)[0] == 200


def test_gevent_auth_lock_waits_do_not_freeze_health_or_bypass_revocation(live_gevent_server, monkeypatch):
    port = live_gevent_server["port"]
    credential = server.connections_store.create("Revocation under contention")
    entered = Event()
    lock = server.connections_store.lock
    monkeypatch.setattr(server.connections_store, "lock", TrackedLock(lock, entered))
    with ThreadPoolExecutor(max_workers=1) as requests:
        lock.acquire()
        authentication = requests.submit(
            loopback_json, port, BASE + "/mcp/auth", None,
            {"Authorization": "Bearer " + credential["token"]}, 8,
        )
        try:
            assert entered.wait(timeout=3)
            assert not authentication.done()
            started = time.monotonic()
            assert loopback_json(port, "/health")[0] == 200
            assert loopback_json(port, BASE + "/mcp/auth")[0] == 401
            assert time.monotonic() - started < 1
            server.connections_store.revoke(credential["connection"]["id"])
        finally:
            lock.release()
        status, result = authentication.result(timeout=4)
        assert status == 401
        assert result["code"] == "unauthorized"


def test_concurrent_first_logins_share_one_durable_cookie_secret(monkeypatch):
    original = server.secrets.token_urlsafe

    def slow_secret(*args, **kwargs):
        time.sleep(0.02)
        return original(*args, **kwargs)

    generated = MagicMock(side_effect=slow_secret)
    monkeypatch.setattr(server.secrets, "token_urlsafe", generated)

    def authenticate(_index):
        browser = TestApp(default_app())
        login(browser)
        return browser.get("/youtube-dl/status").json["success"]

    with ThreadPoolExecutor(max_workers=8) as browsers:
        assert all(browsers.map(authenticate, range(8)))
    generated.assert_called_once()


def test_live_preview_has_a_total_deadline_and_never_publishes_timed_out_metadata(live_gevent_server, monkeypatch):
    entered = Event()
    release = Event()
    finished = Event()
    monkeypatch.setattr(server, "PREVIEW_WORK_TIMEOUT_SECONDS", 0.15)

    def blocked_metadata(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        finished.set()
        return {"id": "one", "title": "Too late", "upload_date": "20260810"}

    monkeypatch.setattr(server, "fetch_media_metadata", blocked_metadata)
    port = live_gevent_server["port"]
    started = time.monotonic()
    try:
        status, result = loopback_json(port, BASE + "/plans", {
            "name": "Bounded preview", "candidates": [{"url": "https://youtu.be/one"}],
        }, AUTH)
        assert entered.is_set()
        assert status == 504
        assert result["code"] == "preview_timeout"
        assert time.monotonic() - started < 1
        assert loopback_json(port, "/health")[0] == 200
        assert server.collections_service.state["plans"] == {}
    finally:
        release.set()
    assert finished.wait(timeout=2)
    assert server.collections_service.state["plans"] == {}
    assert server.pending_queue_jobs() == []


def test_gevent_credential_state_errors_never_log_bearer_arguments(live_gevent_server, capsys):
    token = server.connections_store.create("Private error probe")["token"]
    Path(server.CONNECTIONS_STATE_FILE).write_text("{corrupt state")
    status, result = loopback_json(
        live_gevent_server["port"], BASE + "/mcp/auth", headers={"Authorization": "Bearer " + token},
    )
    assert status == 503 and result["code"] == "state_unavailable"
    output = capsys.readouterr()
    assert token not in output.out + output.err
