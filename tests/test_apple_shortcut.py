import importlib.util
import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "integrations/apple-shortcuts/build_shortcut.py"
SOURCE_PATH = ROOT / "integrations/apple-shortcuts/Download-to-NAS.plist"
SIGNED_PATH = ROOT / "integrations/apple-shortcuts/Download-to-NAS.shortcut"
DOCS_PATH = ROOT / "docs/mobile/assets/Download-to-NAS.shortcut"

SPEC = importlib.util.spec_from_file_location("apple_shortcut_builder", BUILDER_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_committed_shortcut_source_matches_deterministic_builder():
    assert SOURCE_PATH.read_bytes() == builder.source_bytes()


def test_shortcut_installs_configuration_questions_and_contextual_prompts():
    workflow = plistlib.loads(SOURCE_PATH.read_bytes())
    actions = workflow["WFWorkflowActions"]
    identifiers = [item["WFWorkflowActionIdentifier"] for item in actions]
    prompts = [item["Text"] for item in workflow["WFWorkflowImportQuestions"]]
    rendered = SOURCE_PATH.read_text(encoding="utf-8")

    assert len(workflow["WFWorkflowImportQuestions"]) == 4
    assert any("NAS base URL" in prompt for prompt in prompts)
    assert any("dashboard ID" in prompt for prompt in prompts)
    assert any("dashboard password" in prompt for prompt in prompts)
    assert any("Default profile" in prompt for prompt in prompts)
    assert "is.workflow.actions.ask" in identifiers
    assert identifiers.count("is.workflow.actions.choosefrommenu") >= 12
    assert "/youtube-dl/share/context" in rendered
    assert "/youtube-dl/rest" in rendered
    assert "from_timestamp" in rendered
    assert "first10" in rendered
    assert "ios-shortcut" in rendered
    assert "compatible-mp4" in rendered
    assert "2.1" in rendered


def test_signed_shortcut_assets_are_current_and_contain_no_real_credentials():
    assert SIGNED_PATH.read_bytes().startswith(b"AEA1")
    assert SIGNED_PATH.read_bytes() == DOCS_PATH.read_bytes()
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "NAS_ADDRESS" in source
    assert "YOUR_ID" in source
    assert "YOUR_PASSWORD" in source
