import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from runtime import (
    PROXY_READ_TIMEOUT_SECONDS, ConfigurationError, RuntimeConfig, nginx_config, prepare_runtime, process_specs, public_health,
)


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "run.sh"


FAKE_PROCESS = """
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
name = {"youtube-dl-server.py": "web", "mcp_server.py": "mcp", "nginx": "nginx"}.get(Path(sys.argv[0]).name, "updater")
runtime = Path(os.environ["APP_DIR"]) / ".runtime"
if name == "updater" and len(sys.argv) > 1:
    (runtime / ("updater-" + sys.argv[1] + ".ready")).write_text("ok")
    sys.exit(0)
def stop(signum, frame):
    (runtime / (name + ".stopped")).write_text(str(signum))
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
if os.environ.get("SPAWN_CHILD") == name:
    child = "import signal,sys,time; from pathlib import Path; r=Path(sys.argv[1]); signal.signal(signal.SIGTERM, lambda s,f: (r.joinpath('grandchild.stopped').write_text(str(s)), sys.exit(0))); signal.signal(signal.SIGINT, lambda s,f: (r.joinpath('grandchild.stopped').write_text(str(s)), sys.exit(0))); r.joinpath('grandchild.ready').write_text('ok'); time.sleep(30)"
    subprocess.Popen([sys.executable, "-u", "-c", child, str(runtime)])
(runtime / (name + ".ready")).write_text(json.dumps(dict(os.environ)))
if os.environ.get("EXIT_PROCESS") == name:
    sys.exit(int(os.environ.get("EXIT_STATUS", "0")))
while True:
    time.sleep(0.05)
"""


def make_fake_app(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "Auth.json").write_text("{}", encoding="utf-8")
    for name in ("runtime.py", "nginx.conf.template"):
        shutil.copyfile(ROOT / name, app_dir / name)
    for name in ("youtube-dl-server.py", "mcp_server.py", "upd_schedule.py"):
        (app_dir / name).write_text(FAKE_PROCESS, encoding="utf-8")
    bin_dir = app_dir / "bin"
    bin_dir.mkdir()
    nginx = bin_dir / "nginx"
    nginx.write_text("#!" + sys.executable + "\n" + FAKE_PROCESS, encoding="utf-8")
    nginx.chmod(0o755)
    return app_dir


def entrypoint_env(tmp_path, app_dir):
    env = os.environ.copy()
    for name in (
        "MY_ID", "MY_ID_FILE", "MY_PW", "MY_PW_FILE", "YDLNAS_API_TOKEN", "YDLNAS_API_TOKEN_FILE",
        "APP_PORT", "YDLNAS_WEB_HOST", "YDLNAS_WEB_PORT", "YDLNAS_MCP_PORT", "PUID", "PGID",
        "UMASK", "EXIT_PROCESS", "EXIT_STATUS", "SPAWN_CHILD",
    ):
        env.pop(name, None)
    env.update({
        "APP_DIR": str(app_dir),
        "DOWNLOAD_DIR": str(tmp_path / "downloads"),
        "STATE_DIR": str(tmp_path / "state"),
        "YTDLP_AUTO_UPDATE": "false",
        "NLPTUTTI_AUTO_UPDATE": "false",
        "PATH": os.pathsep.join([str(app_dir / "bin"), str(Path(sys.executable).parent), env.get("PATH", "")]),
    })
    return env


def wait_ready(process, paths):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        if all(path.exists() for path in paths):
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            pytest.fail(f"Runtime exited before readiness: {stdout}\n{stderr}")
        time.sleep(0.02)
    pytest.fail("Runtime did not become ready")


def start_and_stop(env, app_dir, signum=signal.SIGTERM, extra_ready=()):
    process = subprocess.Popen(
        ["/bin/bash", str(ENTRYPOINT)], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        wait_ready(process, [
            *(app_dir / ".runtime" / f"{name}.ready" for name in ("web", "mcp", "nginx")),
            *(app_dir / ".runtime" / name for name in extra_ready),
        ])
        process.send_signal(signum)
        stdout, stderr = process.communicate(timeout=15)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=15)


def run_to_exit(env):
    return subprocess.run(
        ["/bin/bash", str(ENTRYPOINT)], cwd=ROOT, env=env,
        capture_output=True, text=True, check=False, timeout=15,
    )


def test_entrypoint_reads_credentials_and_token_from_secret_files_without_sharing_them(tmp_path):
    secrets = {"MY_ID": "file-user", "MY_PW": 'file-"password\\value\r', "YDLNAS_API_TOKEN": "file-token"}
    app_dir = make_fake_app(tmp_path)
    (app_dir / "Auth.json").write_text('{"MY_ID":"{{MY_ID}}","MY_PW":"{{MY_PW}}","APP_PORT":"{{APP_PORT}}"}')
    env = entrypoint_env(tmp_path, app_dir)
    for name, value in secrets.items():
        path = tmp_path / name.lower()
        path.write_text(value + "\n", encoding="utf-8")
        env[f"{name}_FILE"] = str(path)
    completed = start_and_stop(env, app_dir)
    assert completed.returncode == 128 + signal.SIGTERM, completed.stderr
    web_env = json.loads((app_dir / ".runtime/web.ready").read_text())
    assert all(web_env[name] == value for name, value in secrets.items())
    assert json.loads((app_dir / "Auth.json").read_text())["MY_PW"] == secrets["MY_PW"]
    for name in ("mcp", "nginx"):
        child_env = json.loads((app_dir / ".runtime" / f"{name}.ready").read_text())
        assert not set(secrets).intersection(child_env)
        assert not {name + "_FILE" for name in secrets}.intersection(child_env)
    assert all(value not in completed.stdout + completed.stderr for value in secrets.values())


def test_direct_environment_values_take_precedence_over_secret_files(tmp_path):
    expected = {"MY_ID": "direct-user", "MY_PW": "direct-password", "YDLNAS_API_TOKEN": "direct-token"}
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update(expected)
    for name in expected:
        env[f"{name}_FILE"] = str(tmp_path / "does-not-need-to-exist")
    completed = start_and_stop(env, app_dir)
    assert completed.returncode == 128 + signal.SIGTERM, completed.stderr
    actual = json.loads((app_dir / ".runtime/web.ready").read_text())
    assert all(actual[name] == value for name, value in expected.items())


def test_entrypoint_rejects_missing_and_empty_secret_files_without_leaking_values(tmp_path):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    missing = run_to_exit(dict(env, MY_PW_FILE=str(tmp_path / "missing-secret")))
    assert missing.returncode != 0
    assert "MY_PW_FILE points to a missing or unreadable regular file" in missing.stderr
    empty_path = tmp_path / "empty-secret"
    empty_path.write_text("", encoding="utf-8")
    empty = run_to_exit(dict(env, YDLNAS_API_TOKEN_FILE=str(empty_path)))
    assert empty.returncode != 0
    assert "YDLNAS_API_TOKEN_FILE points to an empty file" in empty.stderr


def test_entrypoint_rejects_an_unreadable_secret_file(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can read files regardless of owner permission bits")
    app_dir = make_fake_app(tmp_path)
    secret_path = tmp_path / "unreadable-secret"
    secret_path.write_text("must-not-appear", encoding="utf-8")
    secret_path.chmod(0)
    env = entrypoint_env(tmp_path, app_dir)
    env["MY_PW_FILE"] = str(secret_path)
    try:
        completed = run_to_exit(env)
    finally:
        secret_path.chmod(0o600)
    assert completed.returncode != 0
    assert "MY_PW_FILE points to a missing or unreadable regular file" in completed.stderr
    assert "must-not-appear" not in completed.stdout + completed.stderr


@pytest.mark.parametrize("values", [
    {"APP_PORT": "8081", "YDLNAS_WEB_PORT": "8081"},
    {"APP_PORT": "8082", "YDLNAS_MCP_PORT": "8082"},
    {"YDLNAS_WEB_PORT": "8082", "YDLNAS_MCP_PORT": "8082"}, {"YDLNAS_MCP_PORT": "8080"},
    {"APP_PORT": "0"}, {"APP_PORT": "65536"}, {"APP_PORT": "8080;worker_processes 99;"},
    {"YDLNAS_WEB_PORT": "bad"}, {"YDLNAS_MCP_PORT": "-2"},
    {"PUID": "not-numeric"}, {"PGID": "-1"}, {"UMASK": "999"},
])
def test_invalid_or_conflicting_ports_and_permissions_fail_before_launch(tmp_path, values):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update(values)
    completed = run_to_exit(env)
    assert completed.returncode != 0
    assert not (app_dir / ".runtime/web.ready").exists()


@pytest.mark.parametrize("public_port,web_port,mcp_port", [
    ("8081", "8083", "8082"), ("8082", "8081", "8083"),
])
def test_existing_public_ports_relocate_implicit_loopback_defaults(tmp_path, public_port, web_port, mcp_port):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env["APP_PORT"] = public_port
    completed = start_and_stop(env, app_dir)
    assert completed.returncode == 143, completed.stderr
    for name in ("web", "mcp"):
        child_env = json.loads((app_dir / ".runtime" / f"{name}.ready").read_text())
        assert child_env["APP_PORT"] == public_port
        assert child_env["YDLNAS_WEB_HOST"] == "127.0.0.1"
        assert child_env["YDLNAS_WEB_PORT"] == web_port
        assert child_env["YDLNAS_MCP_PORT"] == mcp_port
    rendered = (app_dir / ".runtime/nginx.conf").read_text()
    assert f"listen {public_port};" in rendered and rendered.count("listen ") == 1
    assert f"proxy_pass http://127.0.0.1:{web_port};" in rendered
    assert f"proxy_pass http://127.0.0.1:{mcp_port};" in rendered


@pytest.mark.parametrize("env,expected", [
    ({}, (8080, 8081, 8082)),
    ({"YDLNAS_WEB_PORT": "8082"}, (8080, 8082, 8083)),
    ({"YDLNAS_MCP_PORT": "8081"}, (8080, 8082, 8081)),
    ({"APP_PORT": "8081", "YDLNAS_MCP_PORT": "8083"}, (8081, 8082, 8083)),
    ({"APP_PORT": "8082", "YDLNAS_WEB_PORT": "", "YDLNAS_MCP_PORT": ""}, (8082, 8081, 8083)),
])
def test_internal_port_selection_preserves_explicit_nonconflicting_overrides(env, expected):
    config = RuntimeConfig.from_env(env)
    assert (config.app_port, config.web_port, config.mcp_port) == expected


def test_only_nginx_uses_public_port_and_internal_bindings_are_forced_to_loopback(tmp_path):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update({"APP_PORT": "9090", "YDLNAS_WEB_PORT": "9091", "YDLNAS_MCP_PORT": "9092",
                "YDLNAS_WEB_HOST": "0.0.0.0"})
    completed = start_and_stop(env, app_dir)
    assert completed.returncode == 143
    web = json.loads((app_dir / ".runtime/web.ready").read_text())
    assert web["YDLNAS_WEB_HOST"] == "127.0.0.1"
    assert web["YDLNAS_WEB_PORT"] == "9091"
    config = (app_dir / ".runtime/nginx.conf").read_text()
    assert "listen 9090;" in config and config.count("listen ") == 1
    assert "proxy_pass http://127.0.0.1:9091;" in config
    assert "proxy_pass http://127.0.0.1:9092;" in config


@pytest.mark.parametrize("name", ["web", "mcp", "nginx"])
@pytest.mark.parametrize("status", ["0", "7"])
def test_early_core_exit_even_zero_fails_container_and_stops_peers(tmp_path, name, status):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    completed = run_to_exit(dict(env, EXIT_PROCESS=name, EXIT_STATUS=status))
    assert completed.returncode == (7 if status == "7" else 1)
    assert f"{name} exited unexpectedly" in completed.stderr
    assert (app_dir / ".runtime" / f"{name}.ready").exists()
    for other in {"web", "mcp", "nginx"} - {name}:
        marker = app_dir / ".runtime" / f"{other}.ready"
        if marker.exists():
            assert (app_dir / ".runtime" / f"{other}.stopped").exists()


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGINT])
def test_shutdown_propagates_real_signal_to_all_cores_updater_and_grandchildren(tmp_path, signum):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update({"SPAWN_CHILD": "web", "YTDLP_AUTO_UPDATE": "true"})
    completed = start_and_stop(
        env, app_dir, signum, extra_ready=("grandchild.ready", "updater.ready"),
    )
    assert completed.returncode == 128 + signum
    for name in ("web", "mcp", "nginx", "updater", "grandchild"):
        assert (app_dir / ".runtime" / f"{name}.stopped").read_text() == str(signum)


def test_updater_daemon_failure_is_not_silently_ignored(tmp_path):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update({"YTDLP_AUTO_UPDATE": "true", "EXIT_PROCESS": "updater", "EXIT_STATUS": "4"})
    completed = run_to_exit(env)
    assert completed.returncode == 4
    assert "updater exited unexpectedly" in completed.stderr
    assert (app_dir / ".runtime/updater---once.ready").exists()


def test_optional_nlptutti_once_completion_does_not_stop_cores(tmp_path):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env["NLPTUTTI_AUTO_UPDATE"] = "true"
    completed = start_and_stop(env, app_dir, extra_ready=("updater---nlptutti-once.ready",))
    assert completed.returncode == 143
    assert "exited unexpectedly" not in completed.stderr


def test_missing_nginx_binary_is_failure_not_success(tmp_path):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    (app_dir / "bin/nginx").unlink()
    env["PATH"] = str(Path(sys.executable).parent)
    completed = run_to_exit(env)
    assert completed.returncode == 1
    assert "nginx could not start" in completed.stderr


def test_supervisor_escalates_for_a_child_ignoring_shutdown(tmp_path):
    ready = tmp_path / "stubborn.ready"
    child_code = (
        "import signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready)!r}).write_text('ok'); time.sleep(30)"
    )
    runner = (
        "import os,sys; from runtime import ProcessSpec,Supervisor; "
        f"sys.exit(Supervisor(shutdown_timeout=0.2).run([ProcessSpec('stubborn', [sys.executable, '-c', {child_code!r}], dict(os.environ))]))"
    )
    process = subprocess.Popen([sys.executable, "-c", runner], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_ready(process, [ready])
        start = time.monotonic()
        process.terminate()
        process.communicate(timeout=3)
        assert process.returncode == 143
        assert time.monotonic() - start < 2
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=3)


def test_nginx_configuration_preserves_websocket_all_routes_and_private_auth(tmp_path):
    config = RuntimeConfig.from_env({"APP_DIR": str(ROOT), "APP_PORT": "9090"})
    rendered = nginx_config(config)
    assert "@@" not in rendered
    assert "location = /websocket" in rendered
    assert "proxy_set_header Upgrade $http_upgrade;" in rendered
    assert "proxy_set_header Connection $connection_upgrade;" in rendered
    assert "proxy_http_version 1.1;" in rendered
    assert "proxy_buffering off;" in rendered
    assert "proxy_next_upstream off;" in rendered
    assert rendered.count(f"proxy_read_timeout {PROXY_READ_TIMEOUT_SECONDS}s;") == 2
    assert "location / {" in rendered
    assert "location ~ ^/youtube-dl/mcp(?:/|$)" in rendered
    assert 'proxy_set_header Cookie "";' in rendered
    assert "proxy_set_header X-Forwarded-Host $http_host;" in rendered
    assert "map $http_x_forwarded_proto $public_scheme" in rendered
    assert "proxy_set_header X-Forwarded-Proto $public_scheme;" in rendered
    assert "access_log off;" in rendered
    assert "error_log stderr warn;" in rendered
    assert "/dev/stderr" not in rendered
    assert "listen 9090;" in rendered
    assert "client_max_body_size 0;" in rendered
    for name in ("static", "pwa", "youtube-dl/download", "terms"):
        assert f"location /{name}" not in rendered  # All legacy paths fall through unchanged.


def test_all_nginx_temp_directories_are_prepared_for_the_unprivileged_runtime(tmp_path, monkeypatch):
    app_dir = make_fake_app(tmp_path)
    env = entrypoint_env(tmp_path, app_dir)
    env.update(PUID="1000", PGID="1000")
    config = RuntimeConfig.from_env(env)
    chown = MagicMock()
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", chown)
    previous_mask = os.umask(0o022)
    try:
        rendered = prepare_runtime(config, env).read_text()
    finally:
        os.umask(previous_mask)
    for directive, name in (
        ("client_body_temp_path", "client-body"), ("proxy_temp_path", "proxy"),
        ("fastcgi_temp_path", "fastcgi"), ("uwsgi_temp_path", "uwsgi"), ("scgi_temp_path", "scgi"),
    ):
        path = config.runtime_dir / name
        assert path.is_dir()
        assert f'{directive} "{path}";' in rendered
        chown.assert_any_call(path, 1000, 1000, follow_symlinks=False)


def test_auth_json_public_port_fallback_and_runtime_privilege_commands(monkeypatch):
    config = RuntimeConfig.from_env({"APP_DIR": str(ROOT), "PUID": "1000", "PGID": "100"},
                                    {"APP_PORT": "9090"})
    assert config.app_port == 9090
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    specs = process_specs(config, {"YTDLP_AUTO_UPDATE": "false", "NLPTUTTI_AUTO_UPDATE": "false"},
                          ROOT / ".runtime/nginx.conf")
    assert len(specs) == 3
    assert all(spec.command[:2] == ["gosu", "1000:100"] for spec in specs)
    assert all(spec.persistent for spec in specs)
    fallback = RuntimeConfig.from_env({}, {"APP_PORT": "8081"})
    assert (fallback.app_port, fallback.web_port, fallback.mcp_port) == (8081, 8083, 8082)
    with pytest.raises(ConfigurationError, match="distinct"):
        RuntimeConfig.from_env({"YDLNAS_WEB_PORT": "8081"}, {"APP_PORT": "8081"})


def test_only_web_inherits_dashboard_credentials_and_compatibility_token():
    config = RuntimeConfig.from_env({"APP_DIR": str(ROOT)})
    env = {
        "MY_ID": "test-user", "MY_PW": "test-password", "YDLNAS_API_TOKEN": "test-token",
        "YDLNAS_API_TOKEN_FILE": "secret-path", "SECRET_KEY": "cookie-signing-key",
    }
    specs = process_specs(config, env, ROOT / ".runtime/nginx.conf")
    assert {spec.name for spec in specs} == {"web", "mcp", "nginx", "updater"}
    assert next(spec for spec in specs if spec.name == "web").env == env
    assert all(not set(env).intersection(spec.env) for spec in specs if spec.name != "web")


@pytest.mark.parametrize("mcp_status,redirect", [(200, False), (503, False), (200, True)])
def test_healthcheck_uses_both_public_routes_and_does_not_follow_redirects(monkeypatch, mcp_status, redirect):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            if redirect:
                self.send_response(302)
                self.send_header("Location", "http://attacker.invalid/")
                self.end_headers()
                return
            mcp = self.path.endswith("/mcp/health")
            self.send_response(mcp_status if mcp else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", **({} if mcp else {"app": "youtube-dl-nas"})}).encode())

    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid/")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = RuntimeConfig.from_env({"APP_PORT": str(server.server_port)})
        assert public_health(config) is (mcp_status == 200 and not redirect)
        assert calls == (["/health"] if redirect else ["/health", "/youtube-dl/mcp/health"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_docker_contract_keeps_only_one_exposed_port_and_existing_volumes():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.count("EXPOSE ") == 1 and "EXPOSE 8080" in dockerfile
    assert 'VOLUME ["/downfolder", "/usr/src/app/metadata"]' in dockerfile
    assert "nginx" in dockerfile
    assert "runtime.py --healthcheck" in dockerfile
    assert "mcp" in (ROOT / "requirements.txt").read_text()
