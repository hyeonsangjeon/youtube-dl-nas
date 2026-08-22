import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "integrations" / "http-shortcuts" / "shortcuts.json"
ARCHIVE_PATHS = (
    ROOT / "integrations" / "http-shortcuts" / "youtube-dl-nas-http-shortcut.zip",
    ROOT / "docs" / "mobile" / "assets" / "youtube-dl-nas-http-shortcut.zip",
)


def test_android_shortcut_supports_download_profiles():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    payload = json.loads(source)
    shortcuts = payload["categories"][0]["shortcuts"]
    download_shortcut = next(item for item in shortcuts if item["name"] == "Download to NAS")
    request_body = json.loads(download_shortcut["bodyContent"])

    assert payload["title"] == "youtube-dl NAS Android Share"
    assert "compatible-mp4" in source
    assert "audio-opus" in source
    assert request_body["client_version"] == "2.1"


def test_android_shortcut_archives_match_the_editable_source():
    expected = SOURCE_PATH.read_bytes()
    for archive_path in ARCHIVE_PATHS:
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.namelist() == ["shortcuts.json"]
            assert archive.read("shortcuts.json") == expected
