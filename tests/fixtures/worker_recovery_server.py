"""Local transfer/fault fixtures and a real web/Supervisor subprocess harness."""

import errno
import importlib.util
import io
import json
import os
import signal
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event, current_thread
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ERROR = "injected-worker-storage-private-detail"


def media_bytes(job_id):
    return b"original worker recovery fixture\n" + job_id.encode("ascii")


def write_report(directory, name, data):
    destination = directory / name
    staging = destination.with_suffix(destination.suffix + ".pending")
    staging.write_text(json.dumps(data), encoding="utf-8")
    staging.replace(destination)


@contextmanager
def local_transfers(server, downloads, log_path=None):
    transfers = []

    def metadata(url, *args, **kwargs):
        return {
            "id": url.rsplit("/", 1)[-1], "extractor_key": "Youtube",
            "title": "Original recovery fixture", "upload_date": "20260810",
        }

    def transfer(command, **kwargs):
        job = server.active_queue_job
        assert job is not None
        assert command[0] == "yt-dlp"
        relative = "/".join(filter(None, (
            job["target_relative_directory"], job["id"] + ".mp4",
        )))
        target = downloads / relative
        target.write_bytes(media_bytes(job["id"]))
        entry = {"job_id": job["id"], "pid": os.getpid(), "relative_path": relative}
        transfers.append(entry)
        if log_path is not None:
            with log_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry) + "\n")
        completed = {**metadata(job["url"]), "filepath": str(target)}
        return SimpleNamespace(
            stdout=io.StringIO(server.YTDLP_ITEM_PREFIX + json.dumps(completed) + "\n"),
            poll=lambda: 0,
        )

    with (
        patch.object(server, "fetch_media_metadata", metadata),
        patch.object(server, "validate_source_redirects", lambda *args, **kwargs: None),
        patch.object(server, "PREFLIGHT_GRACE_SECONDS", 0),
        patch.object(server.subprocess, "Popen", transfer),
    ):
        yield transfers


@contextmanager
def storage_fault(server, phase):
    import collections_backend as backend

    real_write = backend.atomic_json_write
    real_fsync = os.fsync
    queue_path = Path(server.QUEUE_STATE_FILE)
    fault = {"phase": phase, "hits": 0, "queue_writes_after_failure": 0}

    def fail_directory_sync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EIO, PRIVATE_ERROR)
        return real_fsync(descriptor)

    def write(path, payload, **kwargs):
        is_queue = Path(path) == queue_path
        if is_queue and server.worker_failed_event.is_set():
            fault["queue_writes_after_failure"] += 1
        should_fail = (
            is_queue and phase.startswith("activation_")
            and payload.get("active") is not None and server.active_queue_job is None
        ) or (
            is_queue and phase.startswith("clear_")
            and payload.get("active") is None and server.active_queue_job is not None
        ) or (
            phase == "download_history" and Path(path) == Path(server.download_manager.history_file)
        ) or (
            phase == "collection_observer" and Path(path) == Path(server.COLLECTIONS_STATE_FILE)
            and any(
                reserved["status"] == "completed"
                for batch in payload["batches"].values() for reserved in batch["jobs"]
            )
        )
        if not should_fail or fault["hits"]:
            return real_write(path, payload, **kwargs)
        fault["hits"] += 1
        fault["before_queue"] = queue_path.read_text(encoding="utf-8")
        try:
            if phase.endswith("_after_write"):
                # Exercise a real replace followed by a failed directory fsync.
                with patch.object(os, "fsync", fail_directory_sync):
                    return real_write(path, payload, **kwargs)
            raise OSError(errno.ENOSPC, PRIVATE_ERROR)
        finally:
            fault["after_queue"] = queue_path.read_text(encoding="utf-8")

    with (
        patch.object(server, "atomic_json_write", write),
        patch.object(backend, "atomic_json_write", write),
    ):
        yield fault


def load_server():
    spec = importlib.util.spec_from_file_location("worker_recovery_web", ROOT / "youtube-dl-server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return server


@contextmanager
def stalled_preview(enabled):
    if not enabled:
        yield lambda: None
        return
    started = Event()
    release = Event()
    worker = {}

    def preview():
        worker["thread"] = current_thread()
        started.set()
        release.wait()

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="blocked-preview")
    future = executor.submit(preview)
    try:
        assert started.wait(timeout=5), "Unrelated preview did not start"
        yield lambda: {
            "running": future.running(), "done": future.done(),
            "thread_alive": worker["thread"].is_alive(),
            "daemon": worker["thread"].daemon, "released": release.is_set(),
        }
    finally:
        # Do not release the task: ordinary Python exit must still wait for it.
        # The owning subprocess is terminated by the test if fatal exit regresses.
        executor.shutdown(wait=False)


def run_web(directory, phase):
    from bottle import default_app
    from webtest import TestApp

    server = load_server()
    original_activate = server.set_active_queue_job
    original_start = server.start_download_thread_if_needed
    original_fail = server.mark_worker_failed
    recorded_failure = False

    def activate(job):
        deadline = time.monotonic() + 20
        while not (directory / "release-worker").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Test did not release the worker")
            time.sleep(0.01)
        return original_activate(job)

    def start():
        write_report(directory, "web.started.json", {
            "pid": os.getpid(),
            "queue_ids": [job["id"] for job in server.pending_queue_jobs()],
            "failed": server.worker_failed_event.is_set(),
            "blocked_preview": preview_state(),
        })
        return original_start()

    def fail():
        nonlocal recorded_failure
        original_fail()
        if recorded_failure:
            return
        recorded_failure = True
        # run_server joins the native worker before exiting, so this probe cannot
        # race the adapter's shutdown. The socket readiness probe remains real.
        health = TestApp(default_app()).get("/health", expect_errors=True)
        write_report(directory, "web.failed.json", {
            "pid": os.getpid(), "fault": fault,
            "latched": server.worker_failed_event.is_set(),
            "shutdown": server.shutdown_event.is_set(),
            "health_status": health.status_int, "health": health.json,
            "health_cache_control": health.headers.get("Cache-Control"),
            "blocked_preview": preview_state(),
            "transfers": transfers,
            "queue": Path(server.QUEUE_STATE_FILE).read_text(encoding="utf-8"),
        })

    with (
        stalled_preview(phase == "collection_observer") as preview_state,
        local_transfers(server, Path(os.environ["DOWNLOAD_DIR"]), directory / "transfers.jsonl") as transfers,
        storage_fault(server, phase) as fault,
        patch.object(server, "set_active_queue_job", activate),
        patch.object(server, "start_download_thread_if_needed", start),
        patch.object(server, "mark_worker_failed", fail),
    ):
        server.main()
    return 0


def run_peer(directory):
    def stop(signum, _frame):
        write_report(directory, "peer.stopped.json", {"pid": os.getpid(), "signal": signum})
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    write_report(directory, "peer.ready.json", {"pid": os.getpid()})
    while True:
        time.sleep(0.1)


def run_supervisor(directory, phase):
    from runtime import ProcessSpec, Supervisor

    supervisor = Supervisor(shutdown_timeout=2)
    original_popen = subprocess.Popen
    owned_pids = []

    def record_spawn(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        owned_pids.append(process.pid)
        write_report(directory, "owned-pids.json", owned_pids)
        return process

    specs = [
        ProcessSpec(name, [
            sys.executable, "-u", str(Path(__file__).resolve()), mode, str(directory), phase,
        ], dict(os.environ))
        for name, mode in (("web", "web"), ("test-peer", "peer"))
    ]
    with patch.object(subprocess, "Popen", record_spawn):
        status = supervisor.run(specs)
    write_report(directory, "supervisor.exited.json", {
        "status": status,
        "children": {
            spec.name: {"pid": process.pid, "returncode": process.poll()}
            for spec, process in supervisor.children
        },
    })
    return status


def run_recovery(directory):
    server = load_server()
    assert not server.worker_failed_event.is_set()
    assert not server.shutdown_event.is_set()
    restored_count = server.load_persisted_queue()
    restored = server.pending_queue_jobs()
    server.collections_service.reconcile()
    reconciled = server.pending_queue_jobs()
    drained = Event()
    if not reconciled:
        drained.set()
    original_clear = server.clear_active_queue_job

    def clear():
        original_clear()
        if not server.pending_queue_jobs():
            drained.set()

    with (
        local_transfers(server, Path(os.environ["DOWNLOAD_DIR"]), directory / "transfers.jsonl") as transfers,
        patch.object(server, "clear_active_queue_job", clear),
    ):
        server.start_download_thread_if_needed()
        try:
            deadline = time.monotonic() + 10
            while not drained.wait(0.05):
                assert not server.worker_failed_event.is_set(), "Recovery worker failed"
                assert server.download_thread.is_alive(), "Recovery worker exited early"
                assert time.monotonic() < deadline, "Recovery queue did not drain"
        finally:
            server.shutdown_event.set()
            server.download_thread.join(timeout=5)
        assert not server.download_thread.is_alive()
        assert not server.worker_failed_event.is_set()
    write_report(directory, "recovered.json", {
        "pid": os.getpid(), "restored_count": restored_count,
        "restored": restored, "reconciled_ids": [job["id"] for job in reconciled],
        "transfers": transfers, "failed": server.worker_failed_event.is_set(),
        "worker_alive": server.download_thread.is_alive(),
    })
    return 0


def main():
    sys.path.insert(0, str(ROOT))
    mode, directory = sys.argv[1], Path(sys.argv[2])
    if mode == "supervise":
        return run_supervisor(directory, sys.argv[3])
    if mode == "web":
        return run_web(directory, sys.argv[3])
    if mode == "recover":
        return run_recovery(directory)
    if mode == "peer":
        return run_peer(directory)
    raise ValueError("Unknown fixture mode")


if __name__ == "__main__":
    raise SystemExit(main())
