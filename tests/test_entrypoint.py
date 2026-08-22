import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "run.sh"


def make_fake_app(tmp_path, expected):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "Auth.json").write_text("{}", encoding="utf-8")
    checks = "\n".join(
        f"assert os.environ.get({name!r}) == {value!r}" for name, value in expected.items()
    )
    (app_dir / "youtube-dl-server.py").write_text(
        "import os\n" + checks + "\n",
        encoding="utf-8",
    )
    return app_dir


def entrypoint_env(tmp_path, app_dir):
    env = os.environ.copy()
    env.update({
        "APP_DIR": str(app_dir),
        "DOWNLOAD_DIR": str(tmp_path / "downloads"),
        "STATE_DIR": str(tmp_path / "state"),
        "YTDLP_AUTO_UPDATE": "false",
        "NLPTUTTI_AUTO_UPDATE": "false",
        "PATH": str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", ""),
    })
    for name in (
        "MY_ID", "MY_ID_FILE", "MY_PW", "MY_PW_FILE",
        "YDLNAS_API_TOKEN", "YDLNAS_API_TOKEN_FILE",
    ):
        env.pop(name, None)
    return env


def test_entrypoint_reads_credentials_and_token_from_secret_files(tmp_path):
    secrets = {
        "MY_ID": "file-user",
        "MY_PW": "file-password",
        "YDLNAS_API_TOKEN": "file-token",
    }
    app_dir = make_fake_app(tmp_path, secrets)
    env = entrypoint_env(tmp_path, app_dir)
    for name, value in secrets.items():
        path = tmp_path / name.lower()
        path.write_text(value + "\n", encoding="utf-8")
        env[f"{name}_FILE"] = str(path)

    completed = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert all(value not in completed.stdout + completed.stderr for value in secrets.values())


def test_direct_environment_values_take_precedence_over_secret_files(tmp_path):
    expected = {
        "MY_ID": "direct-user",
        "MY_PW": "direct-password",
        "YDLNAS_API_TOKEN": "direct-token",
    }
    app_dir = make_fake_app(tmp_path, expected)
    env = entrypoint_env(tmp_path, app_dir)
    env.update(expected)
    for name in expected:
        env[f"{name}_FILE"] = str(tmp_path / "does-not-need-to-exist")

    completed = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_entrypoint_rejects_missing_and_empty_secret_files_without_leaking_values(tmp_path):
    app_dir = make_fake_app(tmp_path, {})
    base_env = entrypoint_env(tmp_path, app_dir)

    missing_env = dict(base_env, MY_PW_FILE=str(tmp_path / "missing-secret"))
    missing = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=missing_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "MY_PW_FILE points to a missing or unreadable regular file" in missing.stderr

    empty_path = tmp_path / "empty-secret"
    empty_path.write_text("", encoding="utf-8")
    empty_env = dict(base_env, YDLNAS_API_TOKEN_FILE=str(empty_path))
    empty = subprocess.run(
        ["bash", str(ENTRYPOINT)],
        cwd=ROOT,
        env=empty_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert empty.returncode != 0
    assert "YDLNAS_API_TOKEN_FILE points to an empty file" in empty.stderr


def test_entrypoint_rejects_an_unreadable_secret_file(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can read files regardless of owner permission bits")

    app_dir = make_fake_app(tmp_path, {})
    secret_path = tmp_path / "unreadable-secret"
    secret_path.write_text("must-not-appear", encoding="utf-8")
    secret_path.chmod(0)
    env = entrypoint_env(tmp_path, app_dir)
    env["MY_PW_FILE"] = str(secret_path)
    try:
        completed = subprocess.run(
            ["bash", str(ENTRYPOINT)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        secret_path.chmod(0o600)

    assert completed.returncode != 0
    assert "MY_PW_FILE points to a missing or unreadable regular file" in completed.stderr
    assert "must-not-appear" not in completed.stdout + completed.stderr
