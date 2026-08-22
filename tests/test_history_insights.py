import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSIGHTS_MODULE = ROOT / "static" / "logical_js" / "history-insights.js"
NODE = shutil.which("node")


def aggregate(items, now="2026-08-22T12:00:00"):
    if not NODE:
        pytest.skip("Node.js is unavailable")
    script = """
const insights = require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(insights.aggregate(payload.items, payload.now)));
"""
    completed = subprocess.run(
        [NODE, "-e", script, str(INSIGHTS_MODULE), json.dumps({"items": items, "now": now})],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_history_insights_separate_storage_from_download_activity():
    result = aggregate([
        {
            "status": "completed",
            "timestamp": "2026-08-22T10:00:00",
            "download_type": "video",
            "file_exists": True,
            "file_size_bytes": 100,
            "source": "history",
        },
        {
            "status": "file_only",
            "timestamp": "2026-08-22T09:00:00",
            "download_type": "audio",
            "file_exists": True,
            "file_size_bytes": 50,
            "source": "mounted_folder",
            "metadata_status": "missing",
        },
        {
            "status": "completed",
            "timestamp": "2026-08-16T12:00:00",
            "download_type": "subtitle",
            "file_exists": False,
            "file_size_bytes": 500,
            "source": "history",
        },
        {
            "status": "completed",
            "timestamp": "2026-08-09T12:00:00",
            "download_type": "audio",
            "file_exists": False,
            "source": "history",
        },
        {
            "status": "completed",
            "timestamp": "2026-08-08T23:59:59",
            "download_type": "video",
            "file_exists": False,
            "source": "history",
        },
        {
            "status": "failed",
            "failure_code": "network",
            "timestamp": "2026-08-21T12:00:00",
            "source": "history",
        },
        {
            "status": "canceled",
            "timestamp": "2026-08-20T12:00:00",
            "source": "history",
        },
    ])

    assert result["storedFiles"] == 2
    assert result["storedBytes"] == 150
    assert result["recentCompleted"] == 2
    assert result["completed14"] == 3
    assert result["failedJobs"] == 2
    assert result["typeTotals"]["video"] == {"count": 1, "bytes": 100}
    assert result["typeTotals"]["audio"] == {"count": 1, "bytes": 50}
    assert result["typeTotals"]["subtitle"] == {"count": 0, "bytes": 0}
    assert result["failureReasons"] == [
        {"code": "canceled", "count": 1},
        {"code": "network", "count": 1},
    ]


def test_history_insights_handle_invalid_metadata_and_unknown_failures():
    result = aggregate([
        {
            "status": "completed",
            "timestamp": "not-a-date",
            "download_type": "unexpected",
            "file_exists": True,
            "file_size_bytes": "not-a-size",
            "source": "history",
        },
        {
            "status": "error",
            "failure_code": "private-runtime-detail",
            "source": "history",
        },
        {
            "status": "error",
            "failure_code": "network",
            "source": "mounted_folder",
            "metadata_status": "missing",
        },
    ])

    assert result["storedFiles"] == 1
    assert result["storedBytes"] == 0
    assert result["completed14"] == 0
    assert result["failedJobs"] == 1
    assert result["typeTotals"]["file"] == {"count": 1, "bytes": 0}
    assert result["failureReasons"] == [{"code": "unknown", "count": 1}]


def test_history_insights_frontend_contract_is_loaded_and_actionable():
    template = (ROOT / "static" / "template" / "index.tpl").read_text(encoding="utf-8")
    logic = (ROOT / "static" / "logical_js" / "logic.js").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

    assert template.index("history-insights.js") < template.index("logic.js")
    assert 'id="history-insights-toggle"' in template
    assert 'id="history-detail-backdrop"' in template
    assert "helper.aggregate(historyItems" in logic
    assert 'data-history-type="${type}"' in logic
    assert 'data-history-status="failed"' in logic
    assert "trapHistoryDrawerFocus(event)" in logic
    assert ".detail-drawer.detail-overview-open" in styles
