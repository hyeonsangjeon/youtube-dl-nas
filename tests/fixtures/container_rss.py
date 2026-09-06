"""Measure process RSS inside a Linux container, excluding this probe."""

import os
import json
import sys
from pathlib import Path


def process_rss_bytes(status):
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) != 3 or fields[2] != "kB":
                raise ValueError("Unexpected /proc VmRSS format")
            return int(fields[1]) * 1024
    return 0


def total_rss_bytes(proc=Path("/proc"), own_pid=None):
    return sum(process["rss_bytes"] for process in process_rss_details(proc, own_pid))


def process_rss_details(proc=Path("/proc"), own_pid=None):
    own_pid = os.getpid() if own_pid is None else own_pid
    processes = []
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == own_pid:
            continue
        try:
            status = (process / "status").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        name = next((line.split(":", 1)[1].strip() for line in status.splitlines() if line.startswith("Name:")), "unknown")
        processes.append({"pid": int(process.name), "name": name, "rss_bytes": process_rss_bytes(status)})
    return sorted(processes, key=lambda process: process["pid"])


def reviewed_budget_allows(report, review):
    return bool(
        report["version"] == review["version"]
        and report["platform"] == review["platform"]
        and report["baseline_image"] == review["baseline_image"]
        and report["image_delta_bytes"] <= review["max_image_delta_bytes"]
        and report["idle_rss_delta_bytes"] <= review["max_idle_rss_delta_bytes"]
        and report["candidate_idle_rss_bytes"] <= review["max_candidate_idle_rss_bytes"]
    )


if __name__ == "__main__":
    print(json.dumps(process_rss_details()) if "--details" in sys.argv else total_rss_bytes())
