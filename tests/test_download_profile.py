import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROFILE_MODULE = ROOT / "static" / "logical_js" / "download-profile.js"
NODE = shutil.which("node")


def run_profile_script(body):
    if not NODE:
        pytest.skip("Node.js is unavailable")
    script = f"""
const profile = require(process.argv[1]);
{body}
"""
    completed = subprocess.run(
        [NODE, "-e", script, str(PROFILE_MODULE)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_download_profile_saves_and_restores_supported_modes():
    result = run_profile_script("""
const values = new Map();
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, value),
  removeItem: (key) => values.delete(key)
};
const audio = profile.save(storage, 'audio-m4a');
const restoredAudio = profile.load(storage);
const compatible = profile.save(storage, 'compatible-mp4');
const restoredCompatible = profile.load(storage);
const opus = profile.save(storage, 'audio-opus');
const restoredOpus = profile.load(storage);
const subtitle = profile.save(storage, 'vtt|ko');
const restoredSubtitle = profile.load(storage);
process.stdout.write(JSON.stringify({audio, restoredAudio, compatible, restoredCompatible, opus, restoredOpus, subtitle, restoredSubtitle}));
""")

    assert result["audio"] == {
        "version": 1,
        "mode": "audio",
        "resolution": "audio-m4a",
        "subtitleLanguage": "",
    }
    assert result["restoredAudio"] == result["audio"]
    assert result["compatible"] == {
        "version": 1,
        "mode": "video",
        "resolution": "compatible-mp4",
        "subtitleLanguage": "",
    }
    assert result["restoredCompatible"] == result["compatible"]
    assert result["opus"] == {
        "version": 1,
        "mode": "audio",
        "resolution": "audio-opus",
        "subtitleLanguage": "",
    }
    assert result["restoredOpus"] == result["opus"]
    assert result["subtitle"] == {
        "version": 1,
        "mode": "subtitle",
        "resolution": "vtt",
        "subtitleLanguage": "ko",
    }
    assert result["restoredSubtitle"] == result["subtitle"]


def test_download_profile_rejects_stale_or_corrupt_preferences():
    result = run_profile_script("""
let removed = 0;
const invalidStorage = {
  getItem: () => JSON.stringify({version: 1, mode: 'video', resolution: 'raw-format'}),
  removeItem: () => { removed += 1; }
};
const corruptStorage = {getItem: () => '{broken'};
const blockedStorage = {
  getItem: () => { throw new Error('blocked'); },
  setItem: () => { throw new Error('blocked'); }
};
process.stdout.write(JSON.stringify({
  invalid: profile.load(invalidStorage),
  corrupt: profile.load(corruptStorage),
  blockedLoad: profile.load(blockedStorage),
  blockedSave: profile.save(blockedStorage, 'best'),
  removed
}));
""")

    assert result == {
        "invalid": None,
        "corrupt": None,
        "blockedLoad": None,
        "blockedSave": None,
        "removed": 1,
    }


def test_download_profile_frontend_contract_saves_only_after_queue_success():
    template = (ROOT / "static" / "template" / "index.tpl").read_text(encoding="utf-8")
    logic = (ROOT / "static" / "logical_js" / "logic.js").read_text(encoding="utf-8")

    assert template.index("download-profile.js") < template.index("logic.js")
    success_block = logic[logic.index('success: function(response, status)'):logic.index('error: function(jqXHR, textStatus')]
    assert success_block.index("if (response.duplicate)") < success_block.index("if (response.queued === true)")
    assert "saveDownloadProfile(data.resolution)" in success_block
    assert logic.rindex("restoreDownloadProfile();") < logic.rindex("syncModeFromResolution();")
    assert "YDLNAS_SHARED_URL" in logic
