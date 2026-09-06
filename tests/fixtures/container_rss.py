"""Measure process RSS inside a Linux container, excluding this probe."""

import os
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
    own_pid = os.getpid() if own_pid is None else own_pid
    total = 0
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == own_pid:
            continue
        try:
            status = (process / "status").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        total += process_rss_bytes(status)
    return total


if __name__ == "__main__":
    print(total_rss_bytes())
