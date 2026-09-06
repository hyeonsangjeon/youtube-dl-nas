import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from test_collections import (
    AUTH, BASE, REAL_START_DOWNLOAD_THREAD, approve, backend, client,
    isolated_backend, make_plan, server, stable_public_source_network,
)
from fixtures.worker_recovery_server import PRIVATE_ERROR, local_transfers, media_bytes, storage_fault


ROOT = Path(__file__).resolve().parents[1]
HARNESS = Path(__file__).parent / "fixtures" / "worker_recovery_server.py"
PHASES = (
    "activation_before_write", "activation_after_write", "download_history",
    "collection_observer", "clear_before_write", "clear_after_write",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def durable_ids(snapshot):
    return [
        job["id"] for job in
        ([snapshot["active"]] if snapshot["active"] is not None else []) + snapshot["pending"]
    ]


def seed_jobs(client):
    receipt = approve(client, make_plan(client, [
        {"url": "https://youtu.be/recovery-first"},
        {"url": "https://youtu.be/recovery-second"},
    ]))
    server.enqueue_download("https://youtu.be/recovery-unreserved", "best", "web")
    server.download_manager.save_history()
    return receipt, server.pending_queue_jobs()


@pytest.mark.parametrize("phase", PHASES)
def test_worker_persistence_failure_latches_and_preserves_last_durable_snapshot(
    client, isolated_backend, monkeypatch, capsys, phase,
):
    downloads, _state = isolated_backend
    receipt, jobs = seed_jobs(client)
    ids = [job["id"] for job in jobs]
    queue_path = Path(server.QUEUE_STATE_FILE)
    initial = queue_path.read_text(encoding="utf-8")
    assert client.get("/health").json["queue"]["worker_state"] == "ready"
    # A sentinel bounds this regression even if a broken worker swallows the error.
    server.dl_q.put(None)
    with local_transfers(server, downloads) as transfers, storage_fault(server, phase) as fault:
        with pytest.raises(backend.StateError):
            server.dl_worker()
    assert fault["hits"] == 1
    assert fault["queue_writes_after_failure"] == 0
    assert server.worker_failed_event.is_set()
    assert server.shutdown_event.is_set()
    assert [job["id"] for job in server.pending_queue_jobs()] == ids[1:]
    assert server.dl_q.unfinished_tasks == len(ids)
    saved = queue_path.read_text(encoding="utf-8")
    assert saved == fault["after_queue"]
    snapshot = json.loads(saved)
    assert durable_ids(snapshot) == (ids[1:] if phase == "clear_after_write" else ids)
    if phase == "activation_before_write":
        assert saved == initial == fault["before_queue"]
        assert server.active_queue_job is None
    elif phase == "activation_after_write":
        assert saved != fault["before_queue"]
        assert snapshot["active"]["id"] == ids[0]
        assert server.active_queue_job is None
    else:
        assert server.active_queue_job["id"] == ids[0]
    completed = phase in {"collection_observer", "clear_before_write", "clear_after_write"}
    history = read_json(Path(server.download_manager.history_file))
    assert [item["job_id"] for item in history] == (ids[:1] if completed else [])
    assert [entry["job_id"] for entry in transfers] == ([] if phase.startswith("activation_") else ids[:1])
    reserved = read_json(Path(server.COLLECTIONS_STATE_FILE))["batches"][receipt["batch"]["id"]]["jobs"]
    assert reserved[0]["status"] == ("completed" if phase.startswith("clear_") else "queued")

    for clear_shutdown in (False, True):
        if clear_shutdown:
            server.shutdown_event.clear()
        health = client.get("/health", status=503)
        assert health.json["status"] == "unavailable"
        assert health.json["queue"]["worker_state"] == "failed"
        assert health.headers["Cache-Control"] == "no-store"
        assert PRIVATE_ERROR not in health.text
    assert server.worker_failed_event.is_set()
    with pytest.raises(backend.StateError, match="restart"):
        REAL_START_DOWNLOAD_THREAD()
    assert server.download_thread is None
    with pytest.raises(backend.StateError, match="restart"):
        server.enqueue_download("https://youtu.be/must-not-be-added", "best", "web")
    response = client.post_json(BASE + "/downloads", {
        "url": "https://youtu.be/must-not-be-added", "resolution": "best",
    }, headers=AUTH, status=503)
    assert response.json["code"] == "state_unavailable"
    with pytest.raises(backend.StateError, match="restart"):
        server.persist_queue_state()
    with pytest.raises(backend.StateError, match="restart"):
        server.write_queue_snapshot(None, [])
    run = MagicMock()
    monkeypatch.setattr(server, "run", run)
    server.shutdown_event.set()
    with pytest.raises(backend.StateError, match="restart"):
        server.run_server()
    assert server.shutdown_event.is_set()
    run.assert_not_called()
    assert queue_path.read_text(encoding="utf-8") == saved
    assert [job["id"] for job in server.pending_queue_jobs()] == ids[1:]
    captured = capsys.readouterr()
    assert PRIVATE_ERROR not in captured.out + captured.err


def test_failed_native_worker_is_joined_and_never_replaced(
    client, isolated_backend, monkeypatch,
):
    downloads, _state = isolated_backend
    _receipt, jobs = seed_jobs(client)
    thread_errors = MagicMock()
    monkeypatch.setattr(threading, "excepthook", thread_errors)
    with (
        local_transfers(server, downloads),
        storage_fault(server, "activation_after_write") as fault,
    ):
        try:
            REAL_START_DOWNLOAD_THREAD()
            worker = server.download_thread
            worker.join(timeout=5)
            assert not worker.is_alive(), "Fatal persistence failure left the worker running"
            assert fault["hits"] == 1
            assert server.worker_failed_event.is_set()
            saved = Path(server.QUEUE_STATE_FILE).read_text(encoding="utf-8")
            assert durable_ids(json.loads(saved)) == [job["id"] for job in jobs]
            server.shutdown_event.clear()
            with pytest.raises(backend.StateError, match="restart"):
                REAL_START_DOWNLOAD_THREAD()
            assert server.download_thread is worker
            assert Path(server.QUEUE_STATE_FILE).read_text(encoding="utf-8") == saved
            thread_errors.assert_not_called()
        finally:
            server.shutdown_event.set()
            if server.download_thread is not None:
                server.download_thread.join(timeout=5)
                assert not server.download_thread.is_alive()


def test_main_fast_exits_only_for_typed_download_worker_failure(monkeypatch):
    exit_process = MagicMock()
    run = MagicMock(side_effect=server.DownloadWorkerFailed("Worker restart required"))
    monkeypatch.setattr(server.os, "_exit", exit_process)
    monkeypatch.setattr(server, "run_server", run)
    server.main()
    exit_process.assert_called_once_with(1)
    exit_process.reset_mock()
    for error in (backend.StateError("Other state failure"), RuntimeError("Other runtime failure")):
        run.side_effect = error
        with pytest.raises(type(error)) as caught:
            server.main()
        assert caught.value is error
        exit_process.assert_not_called()


def subprocess_environment(directory, downloads, state, port):
    auth = directory / "Auth.json"
    auth.write_text("{}", encoding="utf-8")
    env = dict(os.environ)
    for name in (
        "MY_ID_FILE", "MY_PW_FILE", "YDLNAS_API_TOKEN_FILE", "SECRET_KEY",
        "YTDLP_COOKIES_FILE", "YTDLP_EXTRA_ARGS", "PROXY",
    ):
        env.pop(name, None)
    env.update({
        "AUTH_FILE": str(auth), "STATE_DIR": str(state), "DOWNLOAD_DIR": str(downloads),
        "APP_DIR": str(directory), "TMPDIR": str(directory),
        "HOME": str(directory), "XDG_CACHE_HOME": str(directory / "cache"),
        "MY_ID": "worker-recovery", "MY_PW": "worker-recovery-fixture-password",
        "TERMS_ACCEPTED": "Y", "YDLNAS_API_TOKEN": "worker-recovery-fixture-token",
        "APP_PORT": str(port), "YDLNAS_WEB_HOST": "127.0.0.1", "YDLNAS_WEB_PORT": str(port),
        "YTDLP_AUTO_UPDATE": "false", "NLPTUTTI_AUTO_UPDATE": "false",
        "YDLNAS_ALLOW_PRIVATE_SOURCES": "false",
        "YDLNAS_STORAGE_WARNING_GB": "0", "YDLNAS_STORAGE_CRITICAL_GB": "0",
    })
    return env


def process_output(directory, mode):
    return "\n".join(
        (directory / f"{mode}.{stream}").read_text(encoding="utf-8")
        for stream in ("stdout", "stderr")
    )


@contextmanager
def fixture_process(directory, env, mode, phase=None):
    command = [sys.executable, "-u", str(HARNESS), mode, str(directory)]
    if phase is not None:
        command.append(phase)
    with (
        (directory / f"{mode}.stdout").open("w", encoding="utf-8") as stdout,
        (directory / f"{mode}.stderr").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, start_new_session=True,
        )
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    owned = directory / "owned-pids.json"
                    if mode == "supervise" and owned.exists():
                        for pid in read_json(owned):
                            try:
                                os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    process.kill()
                    process.wait(timeout=5)


def wait_for_web(process, directory, port):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        assert process.poll() is None, process_output(directory, "supervise")
        if (directory / "peer.ready.json").exists() and (directory / "web.started.json").exists():
            connection = HTTPConnection("127.0.0.1", port, timeout=0.5)
            try:
                connection.request("GET", "/health")
                response = connection.getresponse()
                health = json.loads(response.read())
                assert response.status == 200, health
                assert health["status"] == "ok"
                assert health["queue"]["worker_state"] == "ready"
                return
            except (ConnectionError, TimeoutError):
                pass
            finally:
                connection.close()
        time.sleep(0.02)
    pytest.fail("Real web server did not become healthy:\n" + process_output(directory, "supervise"))


def wait_for_exit(process, directory, mode, timeout=15):
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.fail(f"{mode} did not exit:\n" + process_output(directory, mode))


@pytest.mark.parametrize("phase", [phase for phase in PHASES if phase != "download_history"])
def test_real_web_failure_stops_supervisor_and_new_process_recovers_exactly_once(
    client, isolated_backend, monkeypatch, tmp_path, phase,
):
    downloads, state = isolated_backend
    monkeypatch.setattr(server, "QUEUE_STATE_FILE", str(state / "queue_state.json"))
    monkeypatch.setattr(server.download_manager, "history_file", str(state / "download_history.json"))
    receipt, jobs = seed_jobs(client)
    ids = [job["id"] for job in jobs]
    directory = tmp_path / "processes"
    directory.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = subprocess_environment(directory, downloads, state, port)
    blocked_preview = phase == "collection_observer"
    blocked_state = {
        "running": True, "done": False, "thread_alive": True, "daemon": False, "released": False,
    }
    with fixture_process(directory, env, "supervise", phase) as supervisor:
        wait_for_web(supervisor, directory, port)
        startup = read_json(directory / "web.started.json")
        assert startup["queue_ids"] == ids
        assert not startup["failed"]
        assert startup["blocked_preview"] == (blocked_state if blocked_preview else None)
        (directory / "release-worker").write_text("release", encoding="utf-8")
        status = wait_for_exit(supervisor, directory, "supervise", timeout=5 if blocked_preview else 15)
        assert status > 0, process_output(directory, "supervise")

    failed = read_json(directory / "web.failed.json")
    exited = read_json(directory / "supervisor.exited.json")
    children = exited["children"]
    assert failed["pid"] == children["web"]["pid"] == startup["pid"]
    assert 0 < children["web"]["returncode"] <= 125
    assert exited["status"] == status == children["web"]["returncode"]
    assert children["test-peer"]["returncode"] == 0
    peer = read_json(directory / "peer.stopped.json")
    assert peer["pid"] == read_json(directory / "peer.ready.json")["pid"] == children["test-peer"]["pid"]
    assert peer["signal"] == signal.SIGTERM
    for child in children.values():
        with pytest.raises(ProcessLookupError):
            os.kill(child["pid"], 0)
    assert failed["fault"]["hits"] == 1
    assert failed["fault"]["queue_writes_after_failure"] == 0
    assert failed["latched"] and failed["shutdown"]
    assert failed["blocked_preview"] == (blocked_state if blocked_preview else None)
    assert failed["health_status"] == 503
    assert failed["health"]["status"] == "unavailable"
    assert failed["health"]["queue"]["worker_state"] == "failed"
    assert failed["health_cache_control"] == "no-store"
    assert PRIVATE_ERROR not in process_output(directory, "supervise")
    assert PRIVATE_ERROR not in json.dumps(failed["health"])
    queue_path = state / "queue_state.json"
    assert queue_path.read_text(encoding="utf-8") == failed["queue"] == failed["fault"]["after_queue"]
    saved_ids = durable_ids(read_json(queue_path))
    assert saved_ids == (ids[1:] if phase == "clear_after_write" else ids)
    completed = phase in {"collection_observer", "clear_before_write", "clear_after_write"}
    history_before = read_json(state / "download_history.json")
    assert [row["job_id"] for row in history_before] == (ids[:1] if completed else [])
    completed_mtimes = {
        row["relative_path"]: (downloads / row["relative_path"]).stat().st_mtime_ns
        for row in history_before
    }
    if phase == "collection_observer":
        reserved = read_json(state / "collections.json")["batches"][receipt["batch"]["id"]]["jobs"]
        assert reserved[0]["status"] == "queued"

    # This is a new local process, not a Docker restart or an in-memory reset.
    with fixture_process(directory, env, "recover") as recovery:
        assert wait_for_exit(recovery, directory, "recover") == 0, process_output(directory, "recover")
    recovered = read_json(directory / "recovered.json")
    assert recovered["pid"] != failed["pid"]
    assert recovered["restored_count"] == len(saved_ids)
    assert [job["id"] for job in recovered["restored"]] == saved_ids
    assert all(job["restored"] and job["attempts"] >= 1 for job in recovered["restored"])
    remaining = ids[1:] if completed else ids
    assert recovered["reconciled_ids"] == remaining
    assert [entry["job_id"] for entry in recovered["transfers"]] == remaining
    assert not recovered["failed"] and not recovered["worker_alive"]
    snapshot = read_json(queue_path)
    assert snapshot["active"] is None and snapshot["pending"] == []
    transfers = [
        json.loads(line) for line in (directory / "transfers.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["job_id"] for entry in transfers] == ids
    assert Counter(entry["job_id"] for entry in transfers) == Counter(ids)
    assert {entry["pid"] for entry in transfers} <= {failed["pid"], recovered["pid"]}
    history = read_json(state / "download_history.json")
    assert [row["job_id"] for row in history] == ids
    assert all(row["status"] == "completed" for row in history)
    assert len(list(downloads.rglob("*.mp4"))) == len(ids)
    for row in history:
        assert (downloads / row["relative_path"]).read_bytes() == media_bytes(row["job_id"])
    for relative, mtime in completed_mtimes.items():
        assert (downloads / relative).stat().st_mtime_ns == mtime
    collections = read_json(state / "collections.json")
    reserved = collections["batches"][receipt["batch"]["id"]]["jobs"]
    assert [entry["job"]["id"] for entry in reserved] == ids[:2]
    assert all(entry["status"] == "completed" for entry in reserved)
    members = list(collections["memberships"].values())
    assert {member["job_id"] for member in members} == set(ids[:2])
    assert all(member["status"] == "completed" and member["media"]["file_exists"] for member in members)
