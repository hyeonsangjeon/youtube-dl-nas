---
layout: default
title: 26.0922 validation record
---

# 26.0922 Validation Record

This maintenance release improves library traversal, token activity writes,
abandoned-preview retention, and authentication status. It does not claim that
every documented AI client has been certified.

## Native Clients

Both tested clients used the same normal locally built Linux/ARM64 container
through its single public port on host loopback. Dedicated dashboard-issued
tokens authenticated each client. No production NAS files or credentials were
used. The source was a two-second MP4 generated for the test; private sources
were enabled only in this isolated container.

| Client | Version | Result |
| --- | --- | --- |
| Codex CLI | 0.149.1 | Native HTTP MCP discovery, capabilities, profiles, library and collection reads, preview, separately approved commit, actual download, completed batch, and idempotent repeated approval passed |
| Claude Code | 2.1.267 | The same native workflow passed, with a separate connection token and collection |
| GitHub Copilot / VS Code | Not tested | VS Code was present, but its Copilot extension was not installed |
| Cursor | Not tested | Native client was not installed |
| Gemini CLI | Not tested | Native client was not installed |
| OpenCode | Not tested | Native client was not installed |

Codex's non-interactive default approval policy initially blocked the preview
tool, as expected for a mutating MCP tool. The isolated verification invocation
allowed only the preview and commit tools after operator authorization. This
was an invocation-only setting, not a persisted configuration change or advice
to disable approvals in normal use. Preview and commit were separate invocations.
See [Codex's tool approval settings](https://developers.openai.com/codex/mcp/).

The original approval receipt intentionally remains frozen. Read `get_batch`
for current progress after replaying a commit; an original queued receipt does
not mean the job was enqueued again.

## Local Verification

- Full Python/HTTP/JavaScript-backed regression suite: **453 passed** on Python
  3.11. One existing WebOb `cgi` deprecation warning remains.
- Real container: web and MCP health, non-root runtime, 11-tool discovery,
  two cursor pages, immediate revoked-token rejection (401), and authenticated
  WebSocket upgrade (101) passed.
- Both client-downloaded files were 35,551 bytes and SHA-256-identical to the
  generated source. Completed collections and batches survived a container
  restart; the same protocol/file checks passed again afterward.
- Chrome via Playwright: 1440px desktop and 320px mobile in English, Korean,
  Simplified Chinese, and Polish. Token creation changed from waiting to actual
  authentication after a successful bearer request. Simulated MCP unavailability
  recovered on refresh. No page runtime errors or horizontal overflow were found.
- The Browser plugin was unavailable; the existing Playwright package and
  installed Chrome were used, without adding browser dependencies to the app.

The local ARM64 candidate image measured 291,257,280 bytes. A post-restart idle
sample summed to 151,990,272 bytes of process RSS with startup updaters disabled.
This is a single-platform observation, not a peak-memory guarantee or an AMD64
comparison; summed RSS can count shared pages more than once.

## Known Configuration Constraint

The same-configuration restart and image replacement checks passed. An additional
policy-change check found an existing limitation: disabling
`YDLNAS_ALLOW_PRIVATE_SOURCES` after saving collections containing private-source
requests can prevent startup because persisted requests are validated against
the new policy. This release does not change that behavior. Keep the existing
source-policy setting during upgrade; separating persisted-state loading from
admission checks is tracked for a focused follow-up with network-safety tests.

## Publication Checks

The [Docker workflow](https://github.com/hyeonsangjeon/youtube-dl-nas/actions/workflows/docker.yml)
must independently pass Linux/AMD64 startup, authentication and revocation,
WebSocket, loopback isolation, core-failure exit, and the footprint comparison
against `26.0906` before publishing AMD64/ARM64 images. The version-specific RSS
exception for `26.0906` does not apply to this release. The GitHub release job
waits for successful image publication.

The six-primary-client roadmap card remains **In Progress** until the other
four native clients complete the same workflow. Protocol coverage and generated
configuration examples do not substitute for those runs.
