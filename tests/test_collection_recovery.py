import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_collections import (
    AUTH, BASE, approve, backend, client, finish_job, isolated_backend, login,
    make_plan, restart_backend, server, stable_public_source_network,
)


def reused_root_collections(client, downloads):
    path = downloads / "root.mp4"
    path.write_bytes(b"existing media")
    server.download_manager.download_history = [{
        "uuid": "root-media", "filename": path.name, "url": "https://youtu.be/first",
        "resolution": "best", "status": "completed", "title": "Root media",
        "upload_date": "2026-08-10", "media_id": "first", "extractor": "Youtube",
    }]
    server.download_manager.save_history()
    first = approve(client, make_plan(client))
    second = approve(client, make_plan(
        client, name="Another collection",
        criteria={"date_from": "2026-08-01", "date_to": "2026-09-30"},
    ))
    assert server.pending_queue_jobs() == []
    return path, [first, second]


def strip_saved_request_identities():
    state = copy.deepcopy(server.collections_service.state)
    for member in state["memberships"].values():
        member.pop("request", None)
    server.collections_service._save(state)


@pytest.mark.parametrize("already_queued", [False, True])
@pytest.mark.parametrize("history_action", ["keep", "clear", "delete_file"])
@pytest.mark.parametrize("legacy_memberships", [False, True])
def test_reused_missing_media_retry_rebinds_all_members_and_batches(
    client, isolated_backend, monkeypatch, already_queued, history_action, legacy_memberships,
):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    original_ids = {
        row["collection_id"]: row["id"] for row in server.collections_service.state["memberships"].values()
    }
    policies = {
        batch["id"]: copy.deepcopy(batch["items"][0]["date_policy"])
        for batch in server.collections_service.state["batches"].values()
    }
    if legacy_memberships:
        strip_saved_request_identities()
    login(client)
    if history_action == "delete_file":
        client.post("/youtube-dl/history/delete-file/root-media")
    else:
        path.unlink()
        if history_action == "clear":
            client.post("/youtube-dl/history/clear")
    restart_backend(monkeypatch)
    for receipt in receipts:
        detail = server.collections_service.get_collection(receipt["collection"]["id"])
        assert detail["items"][0]["status"] == "missing"
        assert detail["items"][0]["job_id"] is None
    replacement = None
    if already_queued:
        replacement = server.enqueue_download("https://youtu.be/first", "best", "web")["job"]
    retried = client.post("/youtube-dl/history/retry/root-media").json
    assert retried["queued"] is (not already_queued)
    if already_queued:
        assert retried["duplicate_type"] == "queue"
        assert retried["job"]["id"] == replacement["id"]
    jobs = server.pending_queue_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert bool(job["target_relative_directory"]) is (not already_queued)
    for receipt in receipts:
        detail = server.collections_service.get_collection(receipt["collection"]["id"])
        assert detail["collection"]["item_count"] == 1
        assert detail["items"][0]["membership_id"] == original_ids[receipt["collection"]["id"]]
        assert detail["items"][0]["job_id"] == job["id"]
        assert not detail["items"][0]["file_exists"]
        batch = server.collections_service.get_batch(receipt["batch"]["id"])
        assert batch["items"][0]["job_id"] == job["id"]
        assert batch["items"][0]["action"] == ("existing_queue" if already_queued else "queued")
        assert batch["progress"]["queued"] == 1
    completed = finish_job(downloads, job)
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    for receipt in receipts:
        collection_id = receipt["collection"]["id"]
        detail = server.collections_service.get_collection(collection_id)
        assert detail["collection"]["item_count"] == 1
        assert detail["items"][0]["status"] == "completed"
        assert detail["items"][0]["relative_path"] == completed["relative_path"]
        assert detail["items"][0]["membership_id"] == original_ids[collection_id]
        batch = server.collections_service.get_batch(receipt["batch"]["id"])
        assert batch["progress"]["completed"] == 1
        assert batch["items"][0]["uuid"] == completed["uuid"]
        assert batch["items"][0]["relative_path"] == completed["relative_path"]
        assert server.collections_service.state["batches"][batch["id"]]["items"][0]["date_policy"] == policies[batch["id"]]
        assert server.collections_service.commit(receipt["batch"]["plan_id"], {}) == receipt
    client.post("/youtube-dl/history/clear")
    client.delete(BASE + "/collections/" + receipts[0]["collection"]["id"], headers=AUTH)
    restart_backend(monkeypatch)
    assert len(server.collections_service.list_collections()) == 1
    assert server.collections_service.get_collection(receipts[1]["collection"]["id"])["items"][0]["file_exists"]
    assert (downloads / completed["relative_path"]).read_bytes() == b"media"
    assert server.pending_queue_jobs() == []


def test_reused_retry_can_attach_by_media_identity_to_a_different_queued_url(client, isolated_backend):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    path.unlink()
    replacement = server.create_queue_job("https://video.example/alias", "best", "api")
    replacement.update(media_id="first", extractor="youtube")
    server.apply_collection_queue_journal([replacement])
    login(client)
    result = client.post("/youtube-dl/history/retry/root-media").json
    assert result["duplicate_type"] == "queue"
    assert result["job"]["id"] == replacement["id"]
    assert len(server.pending_queue_jobs()) == 1
    finish_job(downloads, replacement)
    for receipt in receipts:
        batch = server.collections_service.get_batch(receipt["batch"]["id"])
        assert batch["progress"]["completed"] == 1
        assert batch["items"][0]["job_id"] == replacement["id"]


def test_preview_aliases_use_the_same_case_insensitive_extractor_identity(client, monkeypatch):
    monkeypatch.setattr(server, "fetch_media_metadata", lambda url, **kwargs: {
        "id": "same-media",
        "extractor_key": "Youtube" if url.endswith("/one") else "youtube",
        "title": "Shared media", "upload_date": "20260810",
    })
    plan = make_plan(client, [{"url": "https://video.example/one"}, {"url": "https://video.example/two"}])
    assert [item["status"] for item in plan["items"]] == ["new", "invalid"]
    assert plan["items"][1]["reason"] == "duplicate_candidate"
    result = approve(client, plan)
    assert result["collection"]["item_count"] == 1
    assert len(server.pending_queue_jobs()) == 1


@pytest.mark.parametrize("completed_first", [False, True])
def test_shared_url_with_conflicting_known_media_identity_keeps_distinct_downloads(
    client, isolated_backend, monkeypatch, completed_first,
):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    first_job = server.pending_queue_jobs()[0]
    if completed_first:
        item = finish_job(downloads, first_job)
        history = server.download_manager.get_history_item(item["uuid"])
        history.update(media_id="first", extractor="Youtube")
        server.download_manager.save_history()
        server.collections_service.reconcile()
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "id": "replacement-media", "extractor_key": "Youtube",
        "title": "Trusted title", "upload_date": "20260810",
    })
    plan = make_plan(client)
    assert plan["items"][0]["status"] == "new"
    second = approve(client, plan, create_collection=False, collection_id=first["collection"]["id"])
    assert second["collection"]["item_count"] == 2
    assert second["batch"]["progress"]["queued"] == 1
    assert second["batch"]["items"][0]["job_id"] != first_job["id"]
    assert len(server.pending_queue_jobs()) == (1 if completed_first else 2)


def test_legacy_reused_snapshot_without_url_can_retry_after_history_was_cleared(
    client, isolated_backend, monkeypatch,
):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    state = copy.deepcopy(server.collections_service.state)
    for member in state["memberships"].values():
        member.pop("request")
        for key in ("url", "media_id", "extractor"):
            member["media"].pop(key, None)
    server.collections_service._save(state)
    server.download_manager.download_history = []
    server.download_manager.save_history()
    path.unlink()
    restart_backend(monkeypatch)
    login(client)
    assert client.post("/youtube-dl/history/retry/root-media").json["queued"]
    job = server.pending_queue_jobs()[0]
    assert job["url"] == "https://youtu.be/first"
    assert job["media_id"] == "first"
    finish_job(downloads, job)
    assert all(
        server.collections_service.get_collection(receipt["collection"]["id"])["items"][0]["status"] == "completed"
        for receipt in receipts
    )


def test_retry_preserves_original_download_options_when_a_collection_links_the_file(client, isolated_backend):
    downloads, _ = isolated_backend
    path, _receipts = reused_root_collections(client, downloads)
    server.download_manager.download_history[0]["write_thumbnail"] = True
    server.download_manager.save_history()
    path.unlink()
    login(client)
    assert client.post("/youtube-dl/history/retry/root-media").json["queued"]
    assert server.pending_queue_jobs()[0]["write_thumbnail"] is True


def test_reused_retry_keeps_each_collections_and_batches_date_restrictions(client, isolated_backend):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    path.unlink()
    queued = server.enqueue_download("https://youtu.be/first", "best", "web")["job"]
    login(client)
    retried = client.post("/youtube-dl/history/retry/root-media").json
    assert retried["job"]["id"] == queued["id"]
    finish_job(downloads, server.pending_queue_jobs()[0], upload_date="2026-09-10")
    first = server.collections_service.get_collection(receipts[0]["collection"]["id"])
    second = server.collections_service.get_collection(receipts[1]["collection"]["id"])
    assert first["items"][0]["status"] == "skipped"
    assert first["items"][0]["failure_code"] == "outside_date_range"
    assert not first["items"][0]["file_exists"]
    assert second["items"][0]["status"] == "completed"
    assert second["items"][0]["file_exists"]
    assert first["batches"][0]["progress"]["skipped"] == 1
    assert second["batches"][0]["progress"]["completed"] == 1
    assert first["batches"][0]["criteria"] == receipts[0]["batch"]["criteria"]
    assert second["batches"][0]["criteria"] == receipts[1]["batch"]["criteria"]


def test_retry_updates_downloaded_and_later_reused_members_of_the_same_media(client, isolated_backend, monkeypatch):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    first_job = server.pending_queue_jobs()[0]
    completed = finish_job(downloads, first_job)
    server.collections_service.reconcile()
    second = approve(client, make_plan(client, name="Linked after completion"))
    assert second["batch"]["progress"]["skipped"] == 1
    (downloads / completed["relative_path"]).unlink()
    login(client)
    result = client.post("/youtube-dl/history/retry/" + completed["uuid"]).json
    job = server.pending_queue_jobs()[0]
    assert result["queued"]
    for receipt in (first, second):
        assert server.collections_service.get_batch(receipt["batch"]["id"])["items"][0]["job_id"] == job["id"]
    finish_job(downloads, job)
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    for receipt in (first, second):
        assert server.collections_service.get_collection(receipt["collection"]["id"])["collection"]["progress"]["completed"] == 1
        assert server.collections_service.get_batch(receipt["batch"]["id"])["progress"]["completed"] == 1


def test_retry_from_an_older_history_row_updates_current_and_newly_linked_members(client, isolated_backend):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    path.unlink()
    login(client)
    assert client.post("/youtube-dl/history/retry/root-media").json["queued"]
    completed = finish_job(downloads, server.pending_queue_jobs()[0])
    server.collections_service.reconcile()
    linked = approve(client, make_plan(client, name="Linked after retry"))
    (downloads / completed["relative_path"]).unlink()
    retried = client.post("/youtube-dl/history/retry/root-media").json
    assert retried["queued"]
    job = server.pending_queue_jobs()[0]
    assert job["target_relative_directory"].startswith("collections/")
    for receipt in receipts + [linked]:
        detail = server.collections_service.get_collection(receipt["collection"]["id"])
        assert detail["items"][0]["job_id"] == job["id"]
    finish_job(downloads, job)
    for receipt in receipts + [linked]:
        assert server.collections_service.get_batch(receipt["batch"]["id"])["progress"]["completed"] == 1


@pytest.mark.parametrize("failure_phase", ["before_queue", "after_queue"])
def test_reused_retry_journal_recovers_after_queue_write_failure(
    client, isolated_backend, monkeypatch, failure_phase,
):
    downloads, _ = isolated_backend
    path, receipts = reused_root_collections(client, downloads)
    path.unlink()
    login(client)
    write = server.write_queue_snapshot

    def fail_write(active, pending):
        if failure_phase == "after_queue":
            write(active, pending)
        raise backend.StateError("Simulated retry persistence failure")

    monkeypatch.setattr(server, "write_queue_snapshot", fail_write)
    client.post("/youtube-dl/history/retry/root-media", status=500, expect_errors=True)
    assert server.pending_queue_jobs() == []
    state = server.collections_service.state
    reserved = state["batches"][receipts[0]["batch"]["id"]]["jobs"][0]["job"]
    assert all(member["job_id"] == reserved["id"] for member in state["memberships"].values())
    monkeypatch.setattr(server, "write_queue_snapshot", write)
    restart_backend(monkeypatch)
    assert [job["id"] for job in server.pending_queue_jobs()] == [reserved["id"]]
    finish_job(downloads, server.pending_queue_jobs()[0])
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    assert all(
        server.collections_service.get_batch(receipt["batch"]["id"])["progress"]["completed"] == 1
        for receipt in receipts
    )


@pytest.mark.parametrize("legacy_memberships", [False, True])
@pytest.mark.parametrize("alias_url", [False, True])
def test_new_batch_redownload_reuses_missing_membership_and_keeps_each_date_policy(
    client, isolated_backend, monkeypatch, legacy_memberships, alias_url,
):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(
        client, criteria={"date_from": "2026-08-01", "date_to": "2026-08-15"},
    ))
    first_job = server.pending_queue_jobs()[0]
    completed = finish_job(downloads, first_job)
    server.collections_service.reconcile()
    original = copy.deepcopy(server.collections_service.get_collection(first["collection"]["id"])["items"][0])
    linked = approve(client, make_plan(client, name="Independent collection"))
    linked_id = server.collections_service.get_collection(linked["collection"]["id"])["items"][0]["membership_id"]
    assert linked_id != original["membership_id"]
    (downloads / completed["relative_path"]).unlink()
    server.download_manager.clear_all_history()
    if legacy_memberships:
        strip_saved_request_identities()
    restart_backend(monkeypatch)
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "id": "first", "extractor_key": "youtube", "title": "Updated title", "upload_date": "20260820",
    })
    next_url = "https://video.example/alias" if alias_url else "https://youtu.be/first"
    plan = make_plan(
        client, [{"url": next_url}],
        criteria={"date_from": "2026-08-16", "date_to": "2026-08-31"},
    )
    second = approve(client, plan, create_collection=False, collection_id=first["collection"]["id"])
    job = server.pending_queue_jobs()[0]
    assert job["id"] != first_job["id"]
    assert job["date_policy"]["date_from"] == "2026-08-16"
    pending = server.collections_service.get_collection(first["collection"]["id"])
    assert pending["collection"]["item_count"] == 1
    assert pending["items"][0]["membership_id"] == original["membership_id"]
    assert pending["items"][0]["job_id"] == job["id"]
    assert server.collections_service.get_batch(first["batch"]["id"])["items"][0]["job_id"] == job["id"]
    finish_job(downloads, job, upload_date="2026-08-20")
    server.collections_service.reconcile()
    detail = server.collections_service.get_collection(first["collection"]["id"])
    assert detail["collection"]["item_count"] == 1
    assert detail["collection"]["progress"]["completed"] == 1
    assert detail["items"][0]["membership_id"] == original["membership_id"]
    assert server.collections_service.get_batch(first["batch"]["id"])["progress"]["skipped"] == 1
    assert server.collections_service.get_batch(first["batch"]["id"])["items"][0]["failure_code"] == "outside_date_range"
    assert server.collections_service.get_batch(second["batch"]["id"])["progress"]["completed"] == 1
    assert server.collections_service.get_batch(first["batch"]["id"])["criteria"] == first["batch"]["criteria"]
    assert server.collections_service.get_batch(second["batch"]["id"])["criteria"] == plan["criteria"]
    assert server.collections_service.get_collection(linked["collection"]["id"])["items"][0]["membership_id"] == linked_id
    server.download_manager.clear_all_history()
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    assert server.collections_service.get_collection(first["collection"]["id"])["collection"]["item_count"] == 1
    login(client)
    client.delete(BASE + "/collections/" + first["collection"]["id"], headers=AUTH)
    assert server.collections_service.get_collection(linked["collection"]["id"])["collection"]["item_count"] == 1
    assert (downloads / completed["relative_path"]).is_file()


@pytest.mark.parametrize("failure_phase", ["before_queue", "after_queue"])
def test_missing_media_redownload_reuses_the_membership_after_partial_commit_recovery(
    client, isolated_backend, monkeypatch, failure_phase,
):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    item = finish_job(downloads, server.pending_queue_jobs()[0])
    server.collections_service.reconcile()
    membership_id = server.collections_service.get_collection(first["collection"]["id"])["items"][0]["membership_id"]
    (downloads / item["relative_path"]).unlink()
    plan = make_plan(client)
    dispatch = server.apply_collection_queue_journal

    def interrupted(jobs, terminal=()):
        if failure_phase == "after_queue":
            dispatch(jobs, terminal)
        raise backend.StateError("Simulated redownload dispatch failure")

    monkeypatch.setattr(server, "apply_collection_queue_journal", interrupted)
    client.post_json(BASE + "/plans/" + plan["id"] + "/commit", {
        "collection_id": first["collection"]["id"], "selected_item_ids": [plan["items"][0]["id"]],
    }, headers=AUTH, status=503)
    receipt = server.collections_service.state["plans"][plan["id"]]["commit_receipt"]
    monkeypatch.setattr(server, "apply_collection_queue_journal", dispatch)
    restart_backend(monkeypatch)
    jobs = server.pending_queue_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == receipt["batch"]["items"][0]["job_id"]
    detail = server.collections_service.get_collection(first["collection"]["id"])
    assert detail["collection"]["item_count"] == 1
    assert detail["items"][0]["membership_id"] == membership_id
    assert server.collections_service.commit(plan["id"], {}) == receipt
    finish_job(downloads, jobs[0])
    restart_backend(monkeypatch)
    assert server.pending_queue_jobs() == []
    detail = server.collections_service.get_collection(first["collection"]["id"])
    assert detail["collection"]["item_count"] == 1
    assert detail["items"][0]["status"] == "completed"


def test_concurrent_new_batches_for_missing_media_share_one_membership_and_job(client, isolated_backend):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    item = finish_job(downloads, server.pending_queue_jobs()[0])
    server.collections_service.reconcile()
    membership_id = next(iter(server.collections_service.state["memberships"]))
    (downloads / item["relative_path"]).unlink()
    plans = [make_plan(client) for _ in range(4)]

    def commit(plan):
        return server.collections_service.commit(plan["id"], {
            "collection_id": first["collection"]["id"],
            "selected_item_ids": [plan["items"][0]["id"]],
        })

    with ThreadPoolExecutor(max_workers=4) as executor:
        receipts = list(executor.map(commit, plans))
    jobs = server.pending_queue_jobs()
    assert len(jobs) == 1
    assert all(receipt["batch"]["items"][0]["job_id"] == jobs[0]["id"] for receipt in receipts)
    assert list(server.collections_service.state["memberships"]) == [membership_id]
    finish_job(downloads, jobs[0])
    detail = server.collections_service.get_collection(first["collection"]["id"])
    assert detail["collection"]["item_count"] == 1
    assert detail["items"][0]["status"] == "completed"
    assert len(detail["batches"]) == 5
    assert all(batch["progress"]["completed"] == 1 for batch in detail["batches"])


@pytest.mark.parametrize("change", ["media_id", "profile", "extractor"])
def test_new_batch_does_not_merge_distinct_media_or_profiles_by_title_or_basename(
    client, isolated_backend, monkeypatch, change,
):
    downloads, _ = isolated_backend
    first = approve(client, make_plan(client))
    completed = finish_job(downloads, server.pending_queue_jobs()[0], name="same-name.mp4")
    server.collections_service.reconcile()
    (downloads / completed["relative_path"]).unlink()
    monkeypatch.setattr(server, "fetch_media_metadata", lambda *args, **kwargs: {
        "id": "other" if change == "media_id" else "first",
        "extractor_key": "Other" if change == "extractor" else "Youtube",
        "title": "Trusted title", "upload_date": "20260810",
    })
    plan = make_plan(client, resolution="720p" if change == "profile" else "best")
    second = approve(client, plan, create_collection=False, collection_id=first["collection"]["id"])
    assert second["collection"]["item_count"] == 2
    finish_job(downloads, server.pending_queue_jobs()[0], name="same-name.mp4")
    detail = server.collections_service.get_collection(first["collection"]["id"])
    assert detail["collection"]["item_count"] == 2
    assert len({item["membership_id"] for item in detail["items"]}) == 2


@pytest.mark.parametrize("options", [
    {"resolution": "audio-mp3"},
    {"playlist_mode": "first10"},
    {"write_thumbnail": True},
    {"section_mode": "from_timestamp", "url": "https://youtu.be/first?t=30"},
])
def test_membership_request_identity_includes_profile_scope_thumbnail_and_sections(
    client, options,
):
    first = approve(client, make_plan(client))
    service = server.collections_service
    member = next(iter(service.state["memberships"].values()))
    job = server.pending_queue_jobs()[0]
    assert service._matches_member_request(service.state, member, job)
    changed = server.normalize_queue_job({**job, **options})
    assert not service._matches_member_request(service.state, member, changed)
    if options.get("section_mode") == "from_timestamp":
        state = copy.deepcopy(service.state)
        state["memberships"][member["id"]]["request"] = service._request_snapshot(changed)
        service._save(state)
        next_section = server.normalize_queue_job({**changed, "url": "https://youtu.be/first?t=60"})
        assert not service._matches_member_request(service.state, state["memberships"][member["id"]], next_section)
    assert service.get_batch(first["batch"]["id"])["criteria"] == first["batch"]["criteria"]
