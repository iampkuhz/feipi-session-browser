# Session HTML Export Contract

This document defines the contract for the session detail HTML export feature.

## Scope

The export produces a single, self-contained HTML file that captures the full
content of a session detail page for offline browsing and archival.

## Contents

The exported HTML MUST include:

- **Session header**: title, agent, model, project, git branch, session key
- **Session metrics**: total tokens, output tokens, cache read/write tokens,
  fresh input tokens, duration, tool call count, failed tool count,
  subagent instance count, user/assistant message count
- **Token composition bar**: visual breakdown of fresh input, cache read,
  cache write, and output tokens
- **Anomaly / diagnostics section**: all detected anomalies with type,
  severity, and reason (when present)
- **All rounds**: every round with call count, tool call count, subagent
  badge, and empty-round signal. No truncation or lazy-loading.
- **Payload source summary**: payload ID, kind, call ID, title, and
  truncation status for each payload source associated with the session
- **Export timestamp**: UTC time of export generation

## Exclusions

The exported HTML MUST NOT include:

- Navigation bar, sidebar, or breadcrumb links
- Links to other sessions or cross-session navigation
- JavaScript lazy-load logic or API fetch calls
- External CSS or JS dependencies (all styles are inlined)
- Dashboard or project links

## Redaction Policy

The export respects the same payload visibility policy as the web UI:

- Under **standard** visibility (default): payload content (request bodies,
  response bodies, tool results) is hidden. Only payload source metadata
  (ID, kind, call ID, title) is shown.
- Under **full** visibility: payload content may be included if the data
  is available and not truncated.

The export route uses `PayloadVisibility.STANDARD` by default. Query parameter
`?visibility=full` enables full payload inclusion.

## Security

- No local absolute file paths appear in the exported HTML
- No `file://` URLs or `C:\` paths
- Content-Disposition is set to `attachment` to prevent inline rendering
- Content-Security-Policy and other security headers are applied
- All dynamic values are Pebble auto-escaped to prevent XSS

## Routes

| Route | Description |
|---|---|
| `GET /sessions/{agent}/{sessionId}/export.html` | Export session as standalone HTML |
| `GET /export/html?agent=...&session_id=...` | Legacy export endpoint (uses same logic) |

## File Naming

Exported file name follows the pattern: `session-{sanitized_session_id}.html`

The session ID is sanitized to contain only alphanumeric characters, hyphens,
and underscores. Maximum length is 100 characters.
