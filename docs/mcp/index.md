---
layout: default
title: MCP Collections and AI Connect
---

# MCP Collections and AI Connect

**Available in 26.0906.** Keep the existing download and metadata volumes when
upgrading. Client configuration examples are not evidence that every client
has passed an end-to-end certification.

## One NAS, One Address

The normal image starts nginx, the existing Bottle/gevent web application,
the official Python MCP SDK's ASGI service, and the enabled updater under one
supervisor. nginx owns the existing `APP_PORT`; the application and MCP services
listen only on internal loopback ports. There is no extra public port, MCP
feature flag, second image, or companion package.

| Public route | Purpose |
| --- | --- |
| `/youtube-dl` | Existing Downloads dashboard |
| `/youtube-dl/collections` | Topic collections and manual batch preview |
| `/youtube-dl/collections/<id>` | Collection metadata, files, and batch progress |
| `/youtube-dl/ai-connect` | Named connection tokens and client setup |
| `/youtube-dl/mcp` | Authenticated Streamable HTTP MCP |
| `/youtube-dl/mcp/health` | MCP readiness, without library data |
| `/websocket` | Existing authenticated live updates |
| `/youtube-dl/api/v1` | Versioned API used by MCP and the new dashboard views |

Keep the existing `/downfolder` and `/usr/src/app/metadata` mounts. The web
application is the only writer for the queue, collections, plans, memberships,
batches, and connection-token registry. MCP forwards authenticated operations
to its loopback API; it does not import the downloader or open state files.

The preferred internal ports are `8081` for web and `8082` for MCP. Defaults
move aside when they conflict with the configured public port. With host
networking, if another host service already occupies an internal port, set
`YDLNAS_WEB_PORT` and `YDLNAS_MCP_PORT` to distinct unused ports. Do not publish
them separately. An upstream HTTPS proxy must preserve the public host and
forward `X-Forwarded-Proto: https`; nginx preserves that scheme for the web
application's same-origin checks.

## Connect A Client

1. Sign in to the dashboard and open **AI Connect**.
2. Give the connection a recognizable name, such as the client and device.
3. Create a token and copy it immediately. It is revealed only in that response;
   the registry stores a hash, never a recoverable secret.
4. Select the client, use the generated same-origin endpoint, and follow its
   configuration instructions. Keep the token outside source control.
5. Discover the server's tools, inspect capabilities and profiles, and start
   with a preview rather than queueing an unreviewed list.

Create a separate token for each client or device. The connection list shows a
safe prefix, creation date, last use, and revocation state. **Revoke** blocks
subsequent requests immediately. It does not cancel batches you already
approved. Dashboard sessions alone do not authenticate MCP, and MCP tokens
cannot manage connection tokens or log in to the dashboard.

An existing `YDLNAS_API_TOKEN` remains compatible. It is configured by the
administrator and is not a dashboard-issued connection, so rotate it in the
container configuration rather than expecting a dashboard revoke button.

### Primary Clients

AI Connect provides native remote-HTTP setup for **Codex**, **Claude Code**,
**GitHub Copilot in VS Code**, **Cursor**, **Gemini CLI**, and **OpenCode**.
Use the official instructions linked beside each generated configuration;
client settings, environment-variable expansion, and secret storage differ.

The generated endpoint uses the address in the browser. If a client connects
through a different VPN hostname or HTTPS reverse proxy, replace that address
with the reachable equivalent, keeping `/youtube-dl/mcp`.

### Native Configuration Examples

The following syntax was checked against official client documentation on
**2026-09-06**. Except for VS Code's secure input, set `YDLNAS_MCP_TOKEN` to the
raw token, **without** a `Bearer ` prefix, in the environment that launches the
client. Preserve the placeholders literally in configuration files. A GUI
application does not inherit variables set later in its integrated terminal.

**Codex — `~/.codex/config.toml`**

```toml
[mcp_servers.youtube-dl-nas]
url = "https://nas.example/youtube-dl/mcp"
bearer_token_env_var = "YDLNAS_MCP_TOKEN"
```

Equivalent CLI:

```shell
codex mcp add youtube-dl-nas \
  --url https://nas.example/youtube-dl/mcp \
  --bearer-token-env-var YDLNAS_MCP_TOKEN
```

[Official Codex instructions](https://developers.openai.com/codex/mcp/).

**Claude Code — project `.mcp.json`**

```json
{
  "mcpServers": {
    "youtube-dl-nas": {
      "type": "http",
      "url": "https://nas.example/youtube-dl/mcp",
      "headers": {"Authorization": "Bearer ${YDLNAS_MCP_TOKEN}"}
    }
  }
}
```

Approve the project server when prompted. Keep `type: http`; the URL alone
does not establish the transport.
[Official HTTP and environment-variable instructions](https://code.claude.com/docs/en/mcp).

**GitHub Copilot in VS Code — `.vscode/mcp.json`**

```json
{
  "servers": {
    "youtube-dl-nas": {
      "type": "http",
      "url": "https://nas.example/youtube-dl/mcp",
      "headers": {"Authorization": "Bearer ${input:ydlnasToken}"}
    }
  },
  "inputs": [
    {
      "id": "ydlnasToken",
      "type": "promptString",
      "description": "youtube-dl-nas MCP token",
      "password": true
    }
  ]
}
```

Use **MCP: Open User Configuration** instead if the server should be user-wide.
VS Code prompts for and securely stores the password input. Run **MCP: List
Servers** and start `youtube-dl-nas`. This recipe targets VS Code's own chat.
Interactive inputs are not forwarded to Agent Host: for that surface, replace
the header with `Bearer ${env:YDLNAS_MCP_TOKEN}` and remove `inputs`.
[Official configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

Copilot CLI is a different client and does not consume `.vscode/mcp.json`.
Its native `copilot mcp add --transport http` setup and `~/.copilot/mcp-config.json`
are documented [separately](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers).
A Copilot CLI run does not count as the VS Code release gate.

**Cursor — `~/.cursor/mcp.json`**

```json
{
  "mcpServers": {
    "youtube-dl-nas": {
      "url": "https://nas.example/youtube-dl/mcp",
      "headers": {"Authorization": "Bearer ${env:YDLNAS_MCP_TOKEN}"}
    }
  }
}
```

Cursor's `envFile` option is for stdio servers, not this remote configuration.
[Official Cursor instructions](https://cursor.com/docs/mcp).

**Gemini CLI — `~/.gemini/settings.json`**

```json
{
  "mcpServers": {
    "youtube-dl-nas": {
      "httpUrl": "https://nas.example/youtube-dl/mcp",
      "headers": {"Authorization": "Bearer ${YDLNAS_MCP_TOKEN}"}
    }
  }
}
```

Use `httpUrl` for Streamable HTTP; `url` selects legacy SSE. Do not set
`trust: true`, which bypasses tool confirmations.
[MCP instructions](https://geminicli.com/docs/tools/mcp-server/) and
[environment substitution](https://geminicli.com/docs/reference/configuration/).

**OpenCode — `~/.config/opencode/opencode.json`**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "youtube-dl-nas": {
      "type": "remote",
      "url": "https://nas.example/youtube-dl/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {"Authorization": "Bearer {env:YDLNAS_MCP_TOKEN}"}
    }
  }
}
```

OpenCode uses `{env:NAME}` **without `$`**. Disable OAuth for this static
bearer-token server.
[Official MCP instructions](https://opencode.ai/docs/mcp-servers/) and
[configuration variables](https://opencode.ai/docs/config/#variables).

### Compatibility-Only Clients

These examples are not additional release gates or claims of tested
authentication. Where environment interpolation is not documented, a literal
`YOUR_MCP_TOKEN` placeholder is intentional. Replace it only in private
user-level configuration.

**Cline** documents `mcpServers` with an explicit `streamableHttp` transport:

```json
{"mcpServers":{"youtube-dl-nas":{"type":"streamableHttp","url":"https://nas.example/youtube-dl/mcp","headers":{"Authorization":"Bearer YOUR_MCP_TOKEN"}}}}
```

[Cline documentation](https://docs.cline.bot/mcp/mcp-overview).
Omitting the transport can select SSE.

**Windsurf legacy Cascade** uses `~/.codeium/windsurf/mcp_config.json`:

```json
{"mcpServers":{"youtube-dl-nas":{"serverUrl":"https://nas.example/youtube-dl/mcp","headers":{"Authorization":"Bearer ${env:YDLNAS_MCP_TOKEN}"}}}}
```

[The official entry point](https://docs.windsurf.com/windsurf/cascade/mcp)
currently redirects to Devin Desktop documentation. This applies to legacy
Cascade, not automatically to the newer Devin Local agent.

**Zed's native Agent** uses `context_servers` in its settings:

```json
{"context_servers":{"youtube-dl-nas":{"url":"https://nas.example/youtube-dl/mcp","headers":{"Authorization":"Bearer YOUR_MCP_TOKEN"}}}}
```

[Zed documentation](https://zed.dev/docs/ai/mcp).
Forwarded external agents are a separate compatibility target.

**LM Studio** documents remote MCP beginning with 0.3.17 build 10:

```json
{"mcpServers":{"youtube-dl-nas":{"url":"https://nas.example/youtube-dl/mcp","headers":{"Authorization":"Bearer YOUR_MCP_TOKEN"}}}}
```

[LM Studio documentation](https://lmstudio.ai/docs/app/mcp).
Do not assume all Cursor environment-interpolation features work here.

**JetBrains AI Assistant** documents native Streamable HTTP with
`mcpServers.<name>.url`, but its cited client instructions do not establish
custom bearer-header support. Treat the authenticated preset as **unverified**,
not a working recipe. Do not confuse the AI Assistant client with the IDE's
separate MCP Server feature.
[JetBrains client instructions](https://www.jetbrains.com/help/ai-assistant/mcp.html).

## Research, Preview, Approve

The **AI client performs web search** and supplies direct media URLs. The NAS
does not search the web or decide what research is relevant.

For example:

> Find publicly available videos I am allowed to download about urban gardening,
> published this year. Preview up to 10 direct URLs for a NAS collection. Show
> dates and duplicates, and wait for my approval before committing.

The preview contains a bounded set of candidates and suggested existing
collections based on normalized names and descriptions. It creates no media
folder or download job. The pending plan itself is saved for 30 minutes so the
same preview can be inspected and then committed once.

| Preview state | What approval can do |
| --- | --- |
| New download | Add one job to the queue |
| Already on NAS | Link the existing file without copying or downloading |
| Already queued | Attach membership to the matching job |
| Invalid or unavailable | Cannot be selected |
| Outside date range | Always excluded, even if explicitly requested |
| Publication date unknown | Unchecked by default; requires explicit selection |

Dates are publication dates reported by source metadata, not the day the file
was downloaded. Candidate-supplied dates are not authoritative. Date bounds
are visible in the plan and are retained with the job; an unknown date is not
silently treated as a date match.

Choose a new or existing collection, select the eligible items, and approve
the commit. Repeating a committed plan returns its stable batch receipt instead
of adding duplicate jobs. If the request times out, inspect or retry that same
plan rather than immediately making a new preview.

Large batches or slow sources can exceed an AI client's own timeout, even
while the NAS is still processing the request. Use a smaller batch if needed,
and inspect the same plan or batch before retrying. A disconnected client is
not a cancellation of already approved work.

Capabilities advertise a 900-second preview transport budget and a 120-second
commit budget. Backend preview work stops publishing results after 840 seconds
and returns `504 preview_timeout`; remaining in-flight probes may finish
cleanup, but cannot enqueue downloads or publish a late plan. Commit uses
trusted preview data without network work; fresh source/date checks still
run at preflight and transfer.

**Collections → Collect URLs** offers the same preview-and-approval flow without
an AI client. Set `YDLNAS_MCP_BATCH_LIMIT` to change the default 25-candidate
limit; administrator values are clamped to 1–100. Playlists and channel URLs
are not batch candidates. The existing Downloads screen retains its explicit
playlist-scope workflow.

## Collection Storage And Removal

New media for a collection is stored at:

```text
/downfolder/collections/<immutable-slug--short-id>/
```

Changing the display name or purpose never renames this folder. Existing root
files stay where they are; a physical file can belong to several collections.
The displayed collection folder is therefore the destination for new files,
not a claim that every linked item physically lives inside it.

Safe nested files participate in mounted-file discovery, search, preview,
browser downloads, thumbnail sidecars, file deletion, and retries. APIs accept
collection and media identifiers, not caller-chosen physical destinations.
Absolute paths, traversal components, and symlinks are rejected. Mounted
subdirectories that are symlinks are not followed.

**Clear Rows** removes history rows, not files, collections, memberships, or
batches. **Remove collection** removes organization metadata, not media or
folders. A file deleted outside the application remains represented as
missing. Use the existing explicit physical-file action in Downloads when
you actually intend to delete media.

Keep the metadata volume when replacing a container. Batch progress is
reconciled against persistent queue and file/history state after restart;
creating a new empty metadata volume is not a recovery mechanism.

If a worker cannot persist a queue transition, `/health` returns 503 and the
web process exits abnormally so the supervisor and configured restart policy
can recover from durable state. It does not resume by clearing a shutdown
flag or executing an unpersisted memory queue. Fix an unavailable or unwritable
metadata volume if the container keeps restarting; do not delete the state
files to make the health check green.

Retrying a missing linked file updates its existing memberships and batch
entries, including references in other collections. A matching job already
in the queue is reused without changing its destination. Adding the same media
to a new batch in the same collection also reuses the membership rather than
creating a second row. Identity includes the media source and download
profile, playlist scope, thumbnail choice, and requested section; a matching
title or basename alone is not sufficient. Each batch retains its own
publication-date policy even when its file or replacement job is shared.

## API Overview

All endpoints below are relative to `/youtube-dl/api/v1`. Data endpoints accept
the signed dashboard session or an authenticated bearer token; connection
management requires the dashboard session. The legacy `/youtube-dl/rest`
interface remains available.

MCP tool names are `get_capabilities`, `list_profiles`, `list_library`,
`get_downloads`, `list_collections`, `get_collection`, `get_plan`, `get_batch`,
`enqueue_download`, `preview_collection`, and `commit_collection`. The commit
tool additionally requires `confirm: true` after approval; this MCP-only
confirmation field is not sent to the REST endpoint.

| Method and path | Result |
| --- | --- |
| `GET /capabilities` | API version, limits, plan lifetime, supported behavior |
| `GET /profiles` | Download profiles |
| `GET /library` | Normalized media and mounted-file rows |
| `GET /downloads` | Queue, active request, and storage state |
| `POST /downloads` | One validated download request |
| `GET /collections` | Collection summaries |
| `GET /collections/<id>` | Collection, members, and batches |
| `PATCH /collections/<id>` | Change display name and description |
| `DELETE /collections/<id>` | Remove organization metadata only |
| `POST /plans` | Validate candidates and save a pending preview |
| `GET /plans/<id>` | Inspect a preview |
| `POST /plans/<id>/commit` | Idempotently approve selected eligible items |
| `GET /batches/<id>` | Live batch receipt |
| `GET /connections` | Redacted connection metadata, dashboard only |
| `POST /connections` | Named connection and one-time token, dashboard only |
| `DELETE /connections/<id>` | Revoke a connection, dashboard only |

Example preview body:

```json
{
  "name": "Urban gardening",
  "description": "Recent tutorials I have permission to save",
  "resolution": "best",
  "criteria": {
    "date_from": "2026-01-01",
    "date_to": "2026-12-31"
  },
  "candidates": [
    {"url": "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"}
  ]
}
```

Use item IDs from the response, not array offsets, when committing:

```json
{
  "create_collection": true,
  "selected_item_ids": ["ITEM_ID_FROM_PREVIEW"],
  "include_unknown_dates": []
}
```

To reuse a collection, send `collection_id` instead of `create_collection`.
If you deliberately selected an unknown-date item, include its ID in both
selection arrays. A server response never needs the client's NAS mount path.

## Network And Permission Boundaries

Bearer authentication is not encryption. Plain HTTP is suitable only for a
trusted private LAN; use HTTPS or a VPN for remote access. Some clients reject
non-loopback HTTP regardless of whether the server can accept it. Do not work
around certificate validation by disabling TLS checks.

The client must be able to reach the NAS address. A cloud-hosted client cannot
normally connect to an RFC1918 address on your home LAN. No tunnel, public
relay, or companion service is installed by this project.

MCP can expose source URLs, titles, and collection metadata to the AI client
you authorize. Consider that client's own data handling. MCP has no
physical-file-delete tool, raw shell tool, or arbitrary filesystem-path input.
Tokens are not put in URLs, browser storage, ordinary logs, or setup examples.

### ChatGPT Is A Separate Deployment Question

ChatGPT's remote connectors/apps run from infrastructure outside your NAS.
A private LAN-only address is not automatically reachable. Custom MCP support
also depends on the ChatGPT plan, workspace settings, and supported
authentication flow. A direct bearer-token setup that works in a local desktop
client is not evidence that it works as a ChatGPT connector.

Consult current OpenAI connector documentation for the chosen plan. This
project does not bundle a tunnel, claim universal ChatGPT support, or expose
the NAS to the Internet automatically.

OpenAI documents OAuth, no-auth, and mixed-auth developer-mode connections,
not this preset's arbitrary static bearer-header configuration. Do not disable
NAS authentication to force compatibility. OpenAI's separately operated Secure
MCP Tunnel requires an additional running client and is outside this image's
no-companion setup.

Plan/write-access descriptions currently differ between the
[developer-mode documentation](https://developers.openai.com/api/docs/guides/developer-mode)
and the [Help Center](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta).
Verify the actual account and administrator policy rather than promising
universal Plus, Pro, or workspace support.

## Validation And Client Compatibility

### Local Evidence And Remaining Gates

The implementation has been exercised through a real local nginx front end,
Bottle/gevent, the official MCP SDK/ASGI service, and the normal supervisor.
An original generated MP4 was downloaded by the real `yt-dlp` process into its
collection folder; its content hash matched the source. Repeated approval kept
one batch, the completed batch survived a full supervisor restart, token
revocation returned 401, and stopping the supervised nginx process produced
a nonzero supervisor exit. The media source was loopback-only with the
private-source opt-in enabled **only for that isolated test**, not a change to
the production default.

Desktop/mobile browser scenarios cover token management, preview selection,
date criteria, idempotency, nested media/range requests, editing without moving
files, clear-history preservation, metadata-only removal, and externally
missing files. All four locales were exercised at a 320-pixel viewport.
The [short demo](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/mcp-collections-demo.gif)
uses labelled synthetic data.

The local Docker daemon returned HTTP 500 even with a compatible API version.
Container smoke and same-platform image/idle-RSS comparisons therefore run in
the [Docker Image workflow](https://github.com/hyeonsangjeon/youtube-dl-nas/actions/workflows/docker.yml)
before image publication; the run summary and `runtime-smoke-evidence` artifact
contain those results. The GitHub release waits for successful image publication.

The first same-platform measurement for `26.0906` found **51.4 MB image
growth** and **107.1 MB additional idle process RSS**, with **157.0 MB total
idle RSS**. The 75 MB RSS review trigger was exceeded, not passed. The
[version-specific design review](footprint-review-26.0906.json) retains the
required separate official SDK service rather than patching SDK internals or
weakening the single-writer/process boundaries. Its exception is limited to
this version and platform, at most 120 MB additional RSS and 180 MB total idle
RSS; future versions do not inherit it. Download-time memory is additional,
and summed process RSS includes shared pages once per process.

**The six primary native clients are not all end-to-end certified in this
release.** The maintainer authorized publication with this limitation disclosed.
Installed CLI/configuration checks, SDK tests, and host import-only memory
observations do not replace native-client runs. The remaining client
certification work stays open on the roadmap.

Use one normal built container when extending this evidence, not a different
test-server configuration for each client:

| Gate | Required evidence |
| --- | --- |
| Each primary native client | Streamable HTTP discovery, bearer auth, read tools, preview, one approved commit, and batch status |
| Filesystem and restart | Existing flat volume, nested files, path/symlink rejection, shared membership, clear-history preservation, interrupted commit recovery |
| Existing integrations | WebSocket upgrade/updates, dashboard actions, PWA share, and legacy REST |
| Desktop and mobile UI | Real navigation, token create/revoke, preview selection, live collection state, edit and metadata-only removal |
| Container process failure | Web/MCP/nginx failure is visible to health and restart handling; stop signals reach children |
| Footprint | Same-platform before/after image size and idle RSS; review if image growth exceeds 100 MB or idle RSS grows by more than 75 MB |
| Publication | One coordinated GitHub release, Docker Hub image, and GHCR image after approval |

Protocol/unit coverage and documentation review are useful evidence, but do
not mark a native client's end-to-end row complete. Compatibility-only clients
are not certification gates. A published version does not imply that the
remaining client certification work is complete.
