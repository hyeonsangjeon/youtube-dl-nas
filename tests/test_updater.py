import subprocess
from unittest.mock import Mock, patch

import upd_schedule


def test_nlptutti_update_uses_runtime_no_cache_upgrade():
    completed = Mock(returncode=0, stdout="ok", stderr="")
    with patch.object(upd_schedule, "get_python_package_version", side_effect=["not installed", "0.0.0.11"]), \
         patch.object(upd_schedule.subprocess, "run", return_value=completed) as run:
        assert upd_schedule.update_nlptutti() is True

    command = run.call_args.args[0]
    assert command[-7:] == [
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--upgrade",
        "nlptutti",
    ]


def test_nlptutti_update_failure_does_not_raise():
    with patch.object(upd_schedule, "get_python_package_version", return_value="not installed"), \
         patch.object(upd_schedule.subprocess, "run", side_effect=subprocess.TimeoutExpired("pip", 30)):
        assert upd_schedule.update_nlptutti() is False
