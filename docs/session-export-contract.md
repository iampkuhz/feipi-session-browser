# Session HTML / MHTML Export Contract

Java session export is a static offline archive of one published session, not
a copy of the live Session Detail interface.

## Published session content

For a published session with content, both formats include the session identity, export time,
Trace row and call record counts, and total token usage. The archive contains
every indexed call and tool execution in the published snapshot, independent of the live
page's pagination or filters. `R` denotes a confirmed model call; `G` denotes a
logical record group without a confirmed model-call boundary. Trace row and
call record totals are not model API call counts:

- Each call includes its Trace row and call identity, main/subagent scope and
  parent links, the four token components and their provenance, and the
  recorded Request and Response bodies.
- Each tool includes its identity, main/subagent scope, declaring call and
  result-consuming call when recorded, and the recorded input and result.
- Tool summaries preserve unknown, measured zero and positive submillisecond
  durations, plus explicit executor observation provenance when present. They
  never derive duration or parallelism from timestamps. Model duration remains
  unmeasured. Fragment links point from each tool to its declaring record's
  model input/output; IDs in fragment anchors are one-way hashes. HTML supports
  this native in-page navigation; MHTML navigation is browser-dependent as
  described below.
- Each record opens and closes with native browser disclosure controls, using a
  mouse or keyboard. Missing source data is not reconstructed from hidden
  provider state.

HTML is self-contained. MHTML packages the same self-contained HTML as a
`multipart/related` attachment. Neither format needs a running server, external
styles, JavaScript, or network requests. Live tabs, filters, payload modals, and
interactive attribution views are not part of the archive.

Prefer HTML when navigating from a tool to its declaring record's model
input/output. In the tested Chromium, MHTML fragment clicks did not navigate,
even with the target record already expanded; the same HTML links worked.
MHTML still contains the complete content and supports native disclosure
controls, so the corresponding declaring record can be expanded manually.
Both formats include this usage hint. This observed limitation is not a claim
that fragment navigation is unavailable in every browser or MHTML implementation.

Both current compact artifacts and unit-based content use the same full-content
snapshot on all three download routes. Metadata-only rendering is reserved for
sessions with no content; it does not recover unrecorded bodies. Each release
builds a fresh index from the original sources; no old index is reused or migrated.
The manifest counts the actual HTML or MIME-wrapped snapshot bytes (the larger
MHTML size when both formats are requested), without changing the JSON data bundle.

## Visibility, safety, and size

Managed export defaults to `visibility=standard`: it includes recorded bodies
subject to the standard payload masking policy. `visibility=full` selects full
payload visibility, but both modes still apply mandatory export masking to
known sensitive fields, credential patterns, and local home-directory paths.
Completeness means no archive-specific pagination or silent truncation of the
published data, not bypassing those masks or recovering data the source did not
record. Text is HTML-escaped.

Downloads are attachments named `session-{sanitized_session_id}.html` or
`session-{sanitized_session_id}.mhtml`. A download exceeding 50 MiB returns
HTTP 413 instead of a partial archive.

## Routes

| Route | Description |
|---|---|
| `GET /sessions/{agent}/{sessionId}/export.html` | Standalone HTML |
| `GET /export/html?agent=...&session_id=...` | Compatibility route for standalone HTML |
| `GET /export/mhtml?agent=...&session_id=...` | MHTML |
