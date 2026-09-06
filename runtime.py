"""Single-port container runtime and dependency-free public health probe."""

import argparse
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


PREVIEW_TIMEOUT_SECONDS = 900
COMMIT_TIMEOUT_SECONDS = 120
PROXY_READ_TIMEOUT_SECONDS = max(PREVIEW_TIMEOUT_SECONDS, COMMIT_TIMEOUT_SECONDS) + 60


class ConfigurationError(Exception):
    pass


def port_number(value, name):
    text = str(value)
    if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 65535:
        raise ConfigurationError(f"{name} must be an integer between 1 and 65535")
    return int(text)


def resolve_secret_files(env):
    for name in ("MY_ID", "MY_PW", "YDLNAS_API_TOKEN"):
        file_name = name + "_FILE"
        if env.get(name) or not env.get(file_name):
            continue
        path = Path(env[file_name])
        try:
            if not stat.S_ISREG(path.stat().st_mode) or not os.access(path, os.R_OK):
                raise OSError()
            value = path.read_bytes().decode("utf-8").rstrip("\n")
        except (OSError, UnicodeError):
            raise ConfigurationError(
                f"{file_name} points to a missing or unreadable regular file"
            ) from None
        if not value:
            raise ConfigurationError(f"{file_name} points to an empty file")
        env[name] = value


def load_auth_config(app_dir, env, render=False):
    path = app_dir / "Auth.json"
    try:
        source = path.read_text(encoding="utf-8")
        data = json.loads(source)
        if not isinstance(data, dict):
            raise ValueError()
        if render and "{{" in source:
            data = {
                key: re.sub(r"\{\{(.*?)\}\}", lambda m: env.get(m[1], ""), value)
                if isinstance(value, str) else value
                for key, value in data.items()
            }
            path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
            path.chmod(0o600)
        return data
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError("Auth.json could not be read or rendered") from None


@dataclass(frozen=True)
class RuntimeConfig:
    app_dir: Path
    state_dir: Path
    download_dir: Path
    runtime_dir: Path
    app_port: int
    web_port: int
    mcp_port: int
    uid: int
    gid: int
    mask: int

    @classmethod
    def from_env(cls, env, auth=None):
        app_dir = Path(env.get("APP_DIR") or "/usr/src/app").resolve()
        ids = [env.get(name, "0") for name in ("PUID", "PGID")]
        if any(not value.isascii() or not value.isdecimal() for value in ids):
            raise ConfigurationError("PUID and PGID must be numeric")
        if any(int(value) > 2**32 - 2 for value in ids):
            raise ConfigurationError("PUID and PGID are out of range")
        mask = env.get("UMASK", "022")
        if not re.fullmatch(r"[0-7]{1,4}", mask) or int(mask, 8) > 0o777:
            raise ConfigurationError("UMASK must be an octal permission mask")
        public_port = port_number(
            env.get("APP_PORT") or (auth or {}).get("APP_PORT") or "8080", "APP_PORT",
        )
        defaults = {"YDLNAS_WEB_PORT": 8081, "YDLNAS_MCP_PORT": 8082}
        internal = {
            name: port_number(env[name], name) for name in defaults if env.get(name)
        }
        configured = [public_port, *internal.values()]
        if len(set(configured)) != len(configured):
            raise ConfigurationError("APP_PORT and explicitly configured internal ports must be distinct")
        used = set(configured)
        # Keep each available default before relocating only the conflicting ones.
        for name, preferred in defaults.items():
            if name not in internal and preferred not in used:
                internal[name] = preferred
                used.add(preferred)
        for name, preferred in defaults.items():
            if name not in internal:
                candidate = preferred
                while candidate in used:
                    candidate += 1
                internal[name] = candidate
                used.add(candidate)
        return cls(
            app_dir=app_dir,
            state_dir=Path(env.get("STATE_DIR") or app_dir / "metadata").resolve(),
            download_dir=Path(env.get("DOWNLOAD_DIR") or "/downfolder").resolve(),
            runtime_dir=app_dir / ".runtime",
            app_port=public_port, web_port=internal["YDLNAS_WEB_PORT"], mcp_port=internal["YDLNAS_MCP_PORT"],
            uid=int(ids[0]), gid=int(ids[1]), mask=int(mask, 8),
        )


def nginx_config(config):
    # Paths are configuration data, never nginx expressions or shell fragments.
    directory = str(config.runtime_dir)
    if any(ord(char) < 32 for char in directory):
        raise ConfigurationError("APP_DIR contains unsupported nginx path characters")
    def quote_path(name):
        path = str(config.runtime_dir / name)
        return '"' + path.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'

    template = (config.app_dir / "nginx.conf.template").read_text(encoding="utf-8")
    for token, value in {
        "PID_PATH": quote_path("nginx.pid"),
        "BODY_PATH": quote_path("client-body"),
        "PROXY_PATH": quote_path("proxy"),
        "FASTCGI_PATH": quote_path("fastcgi"),
        "UWSGI_PATH": quote_path("uwsgi"),
        "SCGI_PATH": quote_path("scgi"),
        "APP_PORT": config.app_port,
        "WEB_PORT": config.web_port,
        "MCP_PORT": config.mcp_port,
        "PROXY_READ_TIMEOUT": PROXY_READ_TIMEOUT_SECONDS,
    }.items():
        template = template.replace(f"@@{token}@@", str(value))
    return template


def prepare_runtime(config, env):
    paths = [
        config.download_dir, config.download_dir / ".incomplete", config.state_dir,
        config.runtime_dir,
        *(config.runtime_dir / name for name in ("client-body", "proxy", "fastcgi", "uwsgi", "scgi", "home", "cache", "scratch")),
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    config_path = config.runtime_dir / "nginx.conf"
    config_path.write_text(nginx_config(config), encoding="utf-8")
    if os.geteuid() == 0:
        for path in paths + [config_path, config.app_dir / "Auth.json"]:
            os.chown(path, config.uid, config.gid, follow_symlinks=False)
        for path in config.state_dir.iterdir():
            if path.is_file() and not path.is_symlink():
                os.chown(path, config.uid, config.gid, follow_symlinks=False)
    env.update({
        "APP_DIR": str(config.app_dir),
        "APP_PORT": str(config.app_port),
        "STATE_DIR": str(config.state_dir),
        "DOWNLOAD_DIR": str(config.download_dir),
        "YDLNAS_WEB_HOST": "127.0.0.1",
        "YDLNAS_WEB_PORT": str(config.web_port),
        "YDLNAS_MCP_PORT": str(config.mcp_port),
        "HOME": str(config.runtime_dir / "home"),
        "TMPDIR": str(config.runtime_dir / "scratch"),
        "XDG_CACHE_HOME": str(config.runtime_dir / "cache"),
    })
    env.setdefault("YTDLP_UPDATE_LOCK", str(config.runtime_dir / "ytdlp-update.lock"))
    os.umask(config.mask)
    return config_path


def enabled(env, name):
    return env.get(name, "true") in ("true", "1")


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    command: list
    env: dict
    persistent: bool = True


def process_specs(config, env, config_path):
    privilege = []
    if os.geteuid() == 0 and (config.uid != 0 or config.gid != 0):
        privilege = ["gosu", f"{config.uid}:{config.gid}"]
    private_env = {
        key: value for key, value in env.items()
        if key not in {
            "MY_ID", "MY_PW", "YDLNAS_API_TOKEN", "SECRET_KEY",
            "MY_ID_FILE", "MY_PW_FILE", "YDLNAS_API_TOKEN_FILE",
        }
    }
    specs = [
        ProcessSpec("web", privilege + [sys.executable, "-u", str(config.app_dir / "youtube-dl-server.py")], env),
        ProcessSpec("mcp", privilege + [sys.executable, "-u", str(config.app_dir / "mcp_server.py")], private_env),
        ProcessSpec("nginx", privilege + [
            "nginx", "-c", str(config_path), "-p", str(config.runtime_dir), "-g", "daemon off;",
        ], private_env),
    ]
    if enabled(env, "YTDLP_AUTO_UPDATE") or enabled(env, "NLPTUTTI_AUTO_UPDATE"):
        specs.append(ProcessSpec(
            "updater", [sys.executable, "-u", str(config.app_dir / "runtime.py"), "--updater"],
            private_env, persistent=enabled(env, "YTDLP_AUTO_UPDATE"),
        ))
    return specs


class Supervisor:
    def __init__(self, shutdown_timeout=10):
        self.children = []
        self.stop_event = threading.Event()
        self.stop_signal = None
        self.shutdown_timeout = shutdown_timeout

    def request_stop(self, signum, _frame=None):
        self.stop_signal = signum
        self.stop_event.set()

    @staticmethod
    def signal_group(process, signum):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass

    @staticmethod
    def group_alive(process):
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False

    @staticmethod
    def reap_orphans():
        if os.getpid() == 1:
            while True:
                try:
                    if os.waitpid(-1, os.WNOHANG)[0] == 0:
                        break
                except ChildProcessError:
                    break

    def stop(self):
        for _spec, process in self.children:
            self.signal_group(process, self.stop_signal or signal.SIGTERM)
        deadline = time.monotonic() + self.shutdown_timeout
        while True:
            parents_running = [process for _, process in self.children if process.poll() is None]
            if not parents_running:
                self.reap_orphans()
            if not any(self.group_alive(process) for _, process in self.children):
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        # Also clean up grandchildren whose group leader has already exited.
        for _spec, process in self.children:
            self.signal_group(process, signal.SIGKILL)
        for spec, process in self.children:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                print(f"{spec.name} did not exit after SIGKILL", file=sys.stderr, flush=True)
        self.reap_orphans()

    def run(self, specs):
        previous = {
            signum: signal.signal(signum, self.request_stop)
            for signum in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            for spec in specs:
                if self.stop_event.is_set():
                    return 128 + self.stop_signal
                try:
                    process = subprocess.Popen(spec.command, env=spec.env, start_new_session=True)
                except OSError:
                    print(f"{spec.name} could not start", file=sys.stderr, flush=True)
                    return 1
                self.children.append((spec, process))
            completed = set()
            while not self.stop_event.is_set():
                for spec, process in self.children:
                    status = process.poll()
                    if status is None or process.pid in completed:
                        continue
                    if spec.persistent or status != 0:
                        print(f"{spec.name} exited unexpectedly (status {status})", file=sys.stderr, flush=True)
                        return status if 0 < status <= 125 else 1
                    completed.add(process.pid)
                self.children = [
                    (spec, process) for spec, process in self.children
                    if process.pid not in completed or self.group_alive(process)
                ]
                self.stop_event.wait(0.1)
            return 128 + self.stop_signal
        finally:
            self.stop()
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def run_updater(env):
    app_dir = Path(env["APP_DIR"])
    for name, flag, label in (
        ("NLPTUTTI_AUTO_UPDATE", "--nlptutti-once", "nlptutti"),
        ("YTDLP_AUTO_UPDATE", "--once", "yt-dlp"),
    ):
        if enabled(env, name):
            result = subprocess.run([sys.executable, "-u", str(app_dir / "upd_schedule.py"), flag], check=False)
            if result.returncode:
                print(f"Startup {label} update failed; continuing with the installed version", flush=True)
    if enabled(env, "YTDLP_AUTO_UPDATE"):
        os.execv(sys.executable, [sys.executable, "-u", str(app_dir / "upd_schedule.py")])
    return 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_health(config):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for path, expected in (
        ("/health", {"status": "ok", "app": "youtube-dl-nas"}),
        ("/youtube-dl/mcp/health", {"status": "ok"}),
    ):
        try:
            with opener.open(f"http://127.0.0.1:{config.app_port}{path}", timeout=2) as response:
                data = json.loads(response.read(1024 * 1024))
                if response.status != 200 or not isinstance(data, dict):
                    return False
                if any(data.get(key) != value for key, value in expected.items()):
                    return False
        except (OSError, ValueError, urllib.error.URLError):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--healthcheck", action="store_true")
    modes.add_argument("--updater", action="store_true")
    args = parser.parse_args()
    env = dict(os.environ)
    try:
        if args.updater:
            return run_updater(env)
        app_dir = Path(env.get("APP_DIR") or "/usr/src/app")
        if args.healthcheck:
            config = RuntimeConfig.from_env(env, load_auth_config(app_dir, env))
            return 0 if public_health(config) else 1
        resolve_secret_files(env)
        config = RuntimeConfig.from_env(env, load_auth_config(app_dir, env, render=True))
        config_path = prepare_runtime(config, env)
        return Supervisor().run(process_specs(config, env, config_path))
    except (ConfigurationError, OSError):
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, ConfigurationError) else "Runtime preparation failed"
        print(message, file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
