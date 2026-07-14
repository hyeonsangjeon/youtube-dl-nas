import argparse
import fcntl
import os
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version

from apscheduler.schedulers.blocking import BlockingScheduler


UPDATE_INTERVAL_SECONDS = max(300, int(os.environ.get("YTDLP_UPDATE_INTERVAL", "3600")))
UPDATE_TIMEOUT_SECONDS = max(30, int(os.environ.get("YTDLP_UPDATE_TIMEOUT", "300")))
LOCK_FILE = os.environ.get("YTDLP_UPDATE_LOCK", "/tmp/youtube-dl-nas-ytdlp-update.lock")
NLPTUTTI_UPDATE_TIMEOUT_SECONDS = max(30, int(os.environ.get("NLPTUTTI_UPDATE_TIMEOUT", "180")))


def log(message):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def get_ytdlp_version():
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def get_python_package_version(package_name):
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return "not installed"


def update_nlptutti():
    previous_version = get_python_package_version("nlptutti")
    log(f"checking nlptutti update (current: {previous_version})")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--upgrade",
                "nlptutti",
            ],
            capture_output=True,
            text=True,
            timeout=NLPTUTTI_UPDATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log(f"nlptutti update timed out after {NLPTUTTI_UPDATE_TIMEOUT_SECONDS} seconds")
        return False
    except OSError as error:
        log(f"nlptutti update could not start: {error}")
        return False

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown pip error").strip().splitlines()[-1]
        log(f"nlptutti update failed: {detail}")
        return False

    current_version = get_python_package_version("nlptutti")
    if current_version == previous_version:
        log(f"nlptutti is current ({current_version})")
    else:
        log(f"nlptutti updated: {previous_version} -> {current_version}")
    return True


def update_ytdlp():
    with open(LOCK_FILE, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("yt-dlp update skipped because another update is already running")
            return True

        previous_version = get_ytdlp_version()
        log(f"checking yt-dlp update (current: {previous_version})")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-cache-dir",
                    "--upgrade",
                    "yt-dlp[default]",
                ],
                capture_output=True,
                text=True,
                timeout=UPDATE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log(f"yt-dlp update timed out after {UPDATE_TIMEOUT_SECONDS} seconds; keeping {previous_version}")
            return False
        except OSError as error:
            log(f"yt-dlp update could not start: {error}; keeping {previous_version}")
            return False

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown pip error").strip().splitlines()[-1]
            log(f"yt-dlp update failed: {detail}; keeping {previous_version}")
            return False

        current_version = get_ytdlp_version()
        if current_version == previous_version:
            log(f"yt-dlp is current ({current_version})")
        else:
            log(f"yt-dlp updated: {previous_version} -> {current_version}")
        return True


def run_scheduler():
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        update_ytdlp,
        "interval",
        seconds=UPDATE_INTERVAL_SECONDS,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=UPDATE_INTERVAL_SECONDS,
    )
    log(f"yt-dlp updater scheduled every {UPDATE_INTERVAL_SECONDS} seconds")
    scheduler.start()


def main():
    parser = argparse.ArgumentParser(description="Keep yt-dlp current without stopping youtube-dl-nas")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run one yt-dlp update check and exit")
    mode.add_argument("--nlptutti-once", action="store_true", help="install or update nlptutti once and exit")
    args = parser.parse_args()
    if args.nlptutti_once:
        raise SystemExit(0 if update_nlptutti() else 1)
    if args.once:
        raise SystemExit(0 if update_ytdlp() else 1)
    run_scheduler()


if __name__ == "__main__":
    main()
