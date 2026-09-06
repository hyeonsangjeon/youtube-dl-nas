import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from bottle import template


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "static" / "logical_js"
NODE = shutil.which("node")


def run_javascript(source):
    if not NODE:
        pytest.skip("Node.js is unavailable")
    completed = subprocess.run(
        [NODE, "-e", source, str(SCRIPTS)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_preview_selection_never_includes_invalid_or_out_of_range_candidates():
    result = run_javascript("""
const workspace = require(process.argv[1] + '/workspace.js');
const items = [
  {id: 'new', status: 'new'},
  {id: 'existing', status: 'already_downloaded'},
  {id: 'queued', status: 'already_queued'},
  {id: 'unknown', status: 'date_unknown'},
  {id: 'outside', status: 'outside_date_range'},
  {id: 'invalid', status: 'invalid'}
];
process.stdout.write(JSON.stringify([
  workspace.selectionForPlan(items, ['new', 'existing', 'queued', 'outside', 'invalid']),
  workspace.selectionForPlan(items, ['unknown', 'unknown', 'outside']),
  workspace.selectionForPlan(items, [])
]));
""")
    assert result == [
        {
            "selected_item_ids": ["new", "existing", "queued"],
            "include_unknown_dates": [],
        },
        {
            "selected_item_ids": ["unknown"],
            "include_unknown_dates": ["unknown"],
        },
        {"selected_item_ids": [], "include_unknown_dates": []},
    ]


def test_collection_progress_handles_failed_and_missing_items_without_nan():
    result = run_javascript("""
const workspace = require(process.argv[1] + '/workspace.js');
process.stdout.write(JSON.stringify([
  workspace.progressSummary({queued: 2, running: 1, completed: 3, skipped: 2, failed: 1, missing: 1}),
  workspace.progressSummary({queued: -2, running: 'not-a-number', completed: Infinity}),
  workspace.progressSummary(null)
]));
""")
    assert result[0]["total"] == 10
    assert result[0]["percent"] == 70
    assert result[0]["counts"]["missing"] == 1
    assert result[1]["total"] == result[2]["total"] == 0
    assert result[1]["percent"] == result[2]["percent"] == 0


def test_member_badge_preserves_mounted_provenance_without_changing_progress():
    result = run_javascript("""
const workspace = require(process.argv[1] + '/workspace.js');
process.stdout.write(JSON.stringify([
  workspace.memberStatus({status: 'completed', file_exists: true, source: 'mounted_folder'}),
  workspace.memberStatus({status: 'completed', file_exists: true, metadata_status: 'missing'}),
  workspace.memberStatus({status: 'completed', file_exists: true, source: 'history', metadata_status: 'saved'}),
  workspace.memberStatus({status: 'queued', file_exists: false, metadata_status: 'missing'}),
  workspace.memberStatus({status: 'failed', file_exists: true, metadata_status: 'missing'}),
  workspace.memberStatus({status: 'missing', file_exists: false, source: 'mounted_folder'}),
  workspace.progressSummary({completed: 2}).counts.completed
]));
""")
    assert result == ["file_only", "file_only", "completed", "queued", "failed", "missing", 2]


def test_six_client_configs_use_native_transports_and_client_specific_secrets():
    result = run_javascript("""
const clients = require(process.argv[1] + '/mcp-clients.js');
process.stdout.write(JSON.stringify(Object.fromEntries(clients.clientIds.map(id => [
  id, clients.setup(id, 'https://nas.example/youtube-dl/mcp')
]))));
""")
    assert set(result) == {"codex", "claude-code", "vscode", "cursor", "gemini", "opencode"}
    assert 'bearer_token_env_var = "YDLNAS_MCP_TOKEN"' in result["codex"]["config"]
    claude = json.loads(result["claude-code"]["config"])["mcpServers"]["youtube-dl-nas"]
    assert claude["type"] == "http"
    assert claude["headers"]["Authorization"] == "Bearer ${YDLNAS_MCP_TOKEN}"
    vscode = json.loads(result["vscode"]["config"])
    assert vscode["servers"]["youtube-dl-nas"]["headers"]["Authorization"] == "Bearer ${input:ydlnasToken}"
    assert vscode["inputs"][0]["password"] is True
    cursor = json.loads(result["cursor"]["config"])["mcpServers"]["youtube-dl-nas"]
    assert cursor["headers"]["Authorization"] == "Bearer ${env:YDLNAS_MCP_TOKEN}"
    gemini = json.loads(result["gemini"]["config"])["mcpServers"]["youtube-dl-nas"]
    assert gemini["httpUrl"] == "https://nas.example/youtube-dl/mcp"
    assert "url" not in gemini
    assert "trust" not in gemini
    opencode = json.loads(result["opencode"]["config"])["mcp"]["youtube-dl-nas"]
    assert opencode["type"] == "remote"
    assert opencode["oauth"] is False
    assert opencode["headers"]["Authorization"] == "Bearer {env:YDLNAS_MCP_TOKEN}"
    assert all("mcp-remote" not in entry["config"] for entry in result.values())


def test_client_setup_rejects_credentials_and_preserves_the_same_origin_prefix():
    result = run_javascript("""
const clients = require(process.argv[1] + '/mcp-clients.js');
const endpoints = [
  'https://user:password@nas.example/youtube-dl/mcp',
  'https://nas.example/youtube-dl/mcp?token=secret',
  'file:///youtube-dl/mcp',
  'https://nas.example/sse'
];
process.stdout.write(JSON.stringify({
  rejected: endpoints.map(url => {
    try { clients.setup('codex', url); return false; } catch (error) { return error instanceof TypeError; }
  }),
  lan: clients.setup('cursor', 'http://192.168.1.10:8080/youtube-dl/mcp').config
}));
""")
    assert all(result["rejected"])
    assert json.loads(result["lan"])["mcpServers"]["youtube-dl-nas"]["url"] == (
        "http://192.168.1.10:8080/youtube-dl/mcp"
    )


def test_collection_search_includes_nested_paths_and_unicode_names():
    result = run_javascript("""
const workspace = require(process.argv[1] + '/workspace.js');
const items = [
  {id: 1, name: 'Garden', description: 'Urban gardening'},
  {id: 2, title: 'A video', relative_path: 'collections/seoul--abcd/서울.mp4'},
  {id: 3, title: 'ＡＢＣ'}
];
process.stdout.write(JSON.stringify([
  workspace.searchItems(items, 'GARDEN').map(item => item.id),
  workspace.searchItems(items, 'seoul--abcd').map(item => item.id),
  workspace.searchItems(items, '서울').map(item => item.id),
  workspace.searchItems(items, 'abc').map(item => item.id)
]));
""")
    assert result == [[1], [2], [2], [2, 3]]


def test_shared_media_helpers_escape_metadata_and_use_only_uuid_file_routes():
    result = run_javascript("""
const media = require(process.argv[1] + '/media-ui.js');
process.stdout.write(JSON.stringify({
  escaped: media.escapeHtml('<img src=x onerror="alert(1)">'),
  unsafe: media.safeThumbnailUrl('javascript:alert(1)'),
  local: media.safeThumbnailUrl('/static/thumbnail/abc'),
  path: media.fileHref({uuid: '../<x>', relative_path: '/private/file'}, false),
  bytes: media.formatBytes(1024, 'en'),
  invalidBytes: media.formatBytes(Infinity, 'en')
}));
""")
    assert result["escaped"] == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
    assert result["unsafe"] == ""
    assert result["local"] == "/static/thumbnail/abc"
    assert result["path"] == "/static/downfolder/..%2F%3Cx%3E"
    assert result["bytes"] == "1.0 KB"
    assert result["invalidBytes"] == "0 B"


def test_workspace_navigation_deep_links_and_shared_media_are_wired():
    template = (ROOT / "static" / "template" / "index.tpl").read_text(encoding="utf-8")
    logic = (SCRIPTS / "logic.js").read_text(encoding="utf-8")
    workspace = (SCRIPTS / "workspace.js").read_text(encoding="utf-8")

    for route in ("/youtube-dl", "/youtube-dl/collections", "/youtube-dl/ai-connect"):
        assert f'href="{route}"' in template
    assert 'aria-current="page"' in template
    assert 'href="#main-content"' in template
    assert 'src="youtube-dl/static/' not in template
    assert 'href="youtube-dl/static/' not in template
    assert template.index("media-ui.js") < template.index("logic.js")
    assert "requestedHistoryUuid = pageParams.get('item')" in logic
    assert "item.relative_path || ''" in logic
    assert "window.YDLNAS_MEDIA_UI.openPreview(item, translate)" in logic
    assert "media.openPreview(item, t)" in workspace
    assert "window.YDLNAS_MEDIA_UI.trapFocus(event" in logic
    assert "media.trapFocus(event, dialog)" in workspace
    assert "document.querySelector('.media-preview-dialog[open]')" in logic
    assert "criteriaText(plan.criteria)" in workspace


def test_ai_connect_does_not_persist_raw_tokens_in_the_browser():
    workspace = (SCRIPTS / "workspace.js").read_text(encoding="utf-8")
    template = (ROOT / "static" / "template" / "ai-connect.tpl").read_text(encoding="utf-8")

    assert "localStorage" not in workspace
    assert "sessionStorage" not in workspace
    assert "console.log" not in workspace
    assert 'id="connection-token" type="password" readonly' in template
    assert "win.addEventListener('pagehide', clearSecret)" in workspace
    assert "byId('connection-token').value = ''" in workspace
    assert "cache: 'no-store'" in workspace


@pytest.mark.parametrize("page,collection_id", [
    ("downloads", ""),
    ("collections", ""),
    ("collections", "test-collection"),
    ("ai-connect", ""),
])
def test_shared_template_renders_each_route_without_losing_navigation(page, collection_id):
    from i18n import catalog_json, get_translator, locale_options

    rendered = template(
        "static/template/index.tpl",
        template_lookup=[str(ROOT)],
        page=page,
        collection_id=collection_id,
        locale="en",
        locale_json='"en"',
        locale_options=locale_options(),
        locale_next="/youtube-dl",
        translations_json=catalog_json("en"),
        shared_url_json='""',
        userNm="demo-user",
        app_version="test",
        t=get_translator("en"),
    )

    assert rendered.count('id="main-content"') == 1
    assert rendered.count('aria-current="page"') == 1
    assert f'data-page="{page}"' in rendered
    if page == "downloads":
        assert 'id="form1"' in rendered
        assert "/logical_js/logic.js" in rendered
        assert "/logical_js/workspace.js" not in rendered
    else:
        assert 'id="form1"' not in rendered
        assert "/logical_js/workspace.js" in rendered
        assert "/logical_js/logic.js" not in rendered
    if page == "collections":
        assert "Collect URLs" in rendered
        assert 'id="batch-plan"' in rendered
    if page == "ai-connect":
        assert "Save this token now" in rendered
        assert "YOUR_MCP_TOKEN" in rendered
