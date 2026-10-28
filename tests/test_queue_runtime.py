import ast
from pathlib import Path

import pytest

from test_server import server
import collections_backend as backend
from queue_runtime import QueueRuntime


ROOT = Path(__file__).resolve().parents[1]


def providers(**overrides):
    values = {name: (lambda: None) for name in QueueRuntime.OPERATIONS}
    values.update(overrides)
    return values


def test_runtime_rejects_missing_unknown_and_uncallable_providers():
    complete = providers()
    complete.pop("fetch_media_metadata")
    with pytest.raises(TypeError, match="missing fetch_media_metadata"):
        QueueRuntime(**complete)

    with pytest.raises(TypeError, match="unknown subprocess"):
        QueueRuntime(**providers(subprocess=lambda: None))

    with pytest.raises(TypeError, match="not callable download_dir"):
        QueueRuntime(**providers(download_dir="/downfolder"))


def test_runtime_rejects_a_provider_that_cannot_resolve_at_start_up():
    def renamed():
        return missing_server_function  # noqa: F821

    with pytest.raises(TypeError, match=r"cannot resolve fetch_media_metadata \(NameError\)"):
        QueueRuntime(**providers(fetch_media_metadata=renamed))


def test_runtime_reads_each_provider_on_every_call():
    state = {"active": None, "directory": "/first"}
    runtime = QueueRuntime(**providers(
        active_queue_job=lambda: state["active"],
        download_dir=lambda: state["directory"],
        classify_playlist_url=lambda: (lambda value: "single:" + value),
    ))

    assert runtime.active_queue_job() is None
    state["active"] = {"id": "job-1"}
    state["directory"] = "/second"
    assert runtime.active_queue_job() == {"id": "job-1"}
    assert runtime.download_dir() == "/second"
    assert runtime.classify_playlist_url("https://example.com/") == "single:https://example.com/"


def test_server_runtime_resolves_every_operation_to_live_module_state(monkeypatch):
    for name in QueueRuntime.OPERATIONS:
        server.queue_runtime._providers[name]()

    active = {"id": "running-job"}
    monkeypatch.setattr(server, "active_queue_job", active)
    monkeypatch.setattr(server, "DOWNFOLDER_DIR", "/patched/downloads")
    monkeypatch.setattr(server, "classify_playlist_url", lambda value: "patched")

    assert server.queue_runtime.active_queue_job() is active
    assert server.queue_runtime.download_dir() == "/patched/downloads"
    assert server.queue_runtime.classify_playlist_url("https://example.com/") == "patched"
    assert server.queue_runtime.queue_operation_lock is server.queue_operation_lock


def test_collection_service_refuses_the_old_globals_handoff(tmp_path):
    with pytest.raises(TypeError, match="needs a QueueRuntime"):
        backend.CollectionService(server.__dict__, str(tmp_path / "collections.json"))


def test_backend_only_uses_declared_runtime_operations():
    tree = ast.parse((ROOT / "collections_backend.py").read_text(encoding="utf-8"))
    used = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "runtime"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    }

    assert used
    assert used <= QueueRuntime.OPERATIONS
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "server"
        for node in ast.walk(tree)
    )


def test_server_source_has_no_globals_handoff():
    source = (ROOT / "youtube-dl-server.py").read_text(encoding="utf-8")
    assert "globals()" not in source
