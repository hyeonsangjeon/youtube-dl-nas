import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from test_collections import (
    AUTH, BASE, approve, backend, client, isolated_backend, make_plan,
    restart_backend, server, stable_public_source_network,
)


def media_rows(count=1105):
    return [
        {"uuid": f"item-{index:04d}", "title": "Saved media", "timestamp": "2026-09-20T10:00:00+00:00"}
        for index in range(count)
    ]


@pytest.mark.parametrize("order", ["newest", "oldest"])
def test_library_cursor_reads_all_pages_with_stable_timestamp_ties(client, monkeypatch, order):
    rows = media_rows()
    monkeypatch.setattr(server.download_manager, "combined_history", lambda: list(reversed(rows)))
    seen, cursor = [], None
    while True:
        params = {"limit": 500, "sort": order}
        if cursor:
            params["cursor"] = cursor
        page = client.get(BASE + "/library", params=params, headers=AUTH).json
        assert page["total"] == len(rows)
        seen.extend(item["uuid"] for item in page["items"])
        cursor = page["next_cursor"]
        assert page["has_more"] == bool(cursor)
        if not cursor:
            break
    assert seen == [item["uuid"] for item in rows]
    assert len(seen) == len(set(seen))


def test_library_sort_uses_download_time_not_publication_date_and_keeps_unknown_last():
    rows = [
        {"uuid": "old", "timestamp": "2026-09-20T12:00:00+09:00", "upload_date": "2030-01-01"},
        {"uuid": "new", "timestamp": "2026-09-20T10:00:00+00:00", "upload_date": "2000-01-01"},
        {"uuid": "unknown", "timestamp": "invalid"},
        {"uuid": "mounted", "timestamp": "2026-09-20T09:00:00+00:00", "source": "mounted_folder"},
    ]
    assert [row["uuid"] for row in backend.library_page(rows)["items"]] == ["new", "mounted", "old", "unknown"]
    assert [row["uuid"] for row in backend.library_page(rows, order="oldest")["items"]] == ["old", "mounted", "new", "unknown"]


def test_library_cursor_does_not_repeat_rows_when_a_new_download_arrives():
    rows = media_rows(5)
    first = backend.library_page(rows, limit=2)
    rows.insert(0, {"uuid": "incoming", "timestamp": "2026-09-21T00:00:00+00:00"})
    rows.pop(1)
    second = backend.library_page(rows, cursor=first["next_cursor"], limit=3)
    assert [row["uuid"] for row in second["items"]] == ["item-0002", "item-0003", "item-0004"]
    assert second["next_cursor"] is None


def test_library_cursor_is_bound_to_search_and_order_and_handles_empty_results(client, monkeypatch):
    monkeypatch.setattr(server.download_manager, "combined_history", lambda: media_rows(5))
    first = client.get(BASE + "/library", params={"q": "SAVED", "limit": 2}, headers=AUTH).json
    for overrides in ({"q": "other"}, {"sort": "oldest"}):
        params = {"q": "saved", "cursor": first["next_cursor"], **overrides}
        assert client.get(BASE + "/library", params=params, headers=AUTH, status=400).json["code"] == "invalid_cursor"
    empty = client.get(BASE + "/library", params={"q": "absent"}, headers=AUTH).json
    assert empty["items"] == [] and empty["total"] == 0 and empty["next_cursor"] is None
    assert client.get(BASE + "/library", params={"sort": "random"}, headers=AUTH, status=400).json["code"] == "invalid_sort"


@pytest.mark.parametrize("cursor", ["not-base64", "a" * 2049, "W10=", "bnVsbA==", "e30=", base64.b64encode(json.dumps({"version": 1, "context": "bad", "after": [0, float("inf"), "id"]}).encode()).decode()])
def test_library_rejects_malformed_cursor_without_server_error(client, cursor):
    assert client.get(BASE + "/library", params={"cursor": cursor}, headers=AUTH, status=400).json["code"] == "invalid_cursor"


def test_library_rejects_cursor_with_oversized_numeric_timestamp(client):
    cursor = base64.urlsafe_b64encode(json.dumps({
        "version": 1, "context": hashlib.sha256(json.dumps(["", "newest"]).encode()).hexdigest(),
        "after": [0, 10 ** 400, "item"],
    }).encode()).decode()
    assert client.get(BASE + "/library", params={"cursor": cursor}, headers=AUTH, status=400).json["code"] == "invalid_cursor"


@pytest.mark.parametrize("now", [1750000000.1234567, 1750000000.1234562])
def test_connection_usage_writes_once_per_minute_and_revocation_is_immediate(isolated_backend, monkeypatch, now):
    store = server.connections_store
    issued = store.create("Temporary test")
    writes = MagicMock(wraps=backend.atomic_json_write)
    monkeypatch.setattr(backend, "atomic_json_write", writes)
    monkeypatch.setattr(backend.time, "time", lambda: now)
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(store.validate, [issued["token"]] * 20))
    assert writes.call_count == 1
    restarted = backend.ConnectionStore(store.path)
    assert restarted.validate(issued["token"])
    assert writes.call_count == 1
    monkeypatch.setattr(backend.time, "time", lambda: now + 61)
    assert store.validate(issued["token"])
    assert writes.call_count == 2
    restarted.revoke(issued["connection"]["id"])
    assert not store.validate(issued["token"])
    assert writes.call_count == 3


def test_connection_usage_recovers_after_clock_moves_backwards(isolated_backend, monkeypatch):
    store = server.connections_store
    issued = store.create("Temporary test")
    assert store.validate(issued["token"])
    previous = backend.time.time()
    monkeypatch.setattr(backend.time, "time", lambda: previous - 3600)
    assert store.validate(issued["token"])
    assert store.list()[0]["last_used_at"] == backend.utc_timestamp(previous - 3600)


@pytest.mark.parametrize("cleanup", ["write", "read", "restart"])
def test_expired_unapproved_plans_are_pruned_without_losing_committed_receipts(client, monkeypatch, cleanup):
    abandoned = make_plan(client)
    committed = make_plan(client, name="Keep this approval")
    receipt = approve(client, committed)
    expiry = server.collections_service.state["plans"][abandoned["id"]]["expires_at_epoch"]
    monkeypatch.setattr(backend.time, "time", lambda: expiry + backend.EXPIRED_PLAN_RETENTION_SECONDS + 1)
    if cleanup == "write":
        make_plan(client, name="Fresh preview")
    elif cleanup == "read":
        server.collections_service.list_collections()
    else:
        restart_backend(monkeypatch)
    assert abandoned["id"] not in server.collections_service.state["plans"]
    assert committed["id"] in server.collections_service.state["plans"]
    assert server.collections_service.commit(committed["id"], {}) == receipt
    client.get(BASE + "/plans/" + abandoned["id"], headers=AUTH, status=404)
    assert len(server.pending_queue_jobs()) == 1


def test_recently_expired_plan_remains_inspectable_during_retention_window(client, monkeypatch):
    plan = make_plan(client)
    expiry = server.collections_service.state["plans"][plan["id"]]["expires_at_epoch"]
    monkeypatch.setattr(backend.time, "time", lambda: expiry + 1)
    restart_backend(monkeypatch)
    make_plan(client, name="Another preview")
    assert client.get(BASE + "/plans/" + plan["id"], headers=AUTH).json["plan"]["expired"]
    client.post_json(BASE + "/plans/" + plan["id"] + "/commit", {
        "create_collection": True, "selected_item_ids": [plan["items"][0]["id"]],
    }, headers=AUTH, status=410)
