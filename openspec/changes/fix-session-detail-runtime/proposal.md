# Proposal: Fix Session Detail Runtime

## Problem

After installing the seed v2 agent harness, the session detail page (`/sessions/<agent>/<session_id>`) returns HTTP 500 with the error:

```
'ConversationRound' object has no attribute 'title'
```

The root cause is in `src/session_browser/web/routes.py` line 1491, where the `session_rounds` context dict accesses `r.title` on each `ConversationRound` object. The `ConversationRound` dataclass (defined in `src/session_browser/domain/models.py`) has no `title` field — it has `preview_text` instead.

This is a regression introduced during a prior refactor that renamed or removed the `title` field without updating the route's `session_rounds` builder.

## Scope

- Fix the single attribute access bug in `routes.py:1491`.
- Add a smoke test that exercises the session detail route end-to-end using the test client pattern, so this class of regression is caught before merge.
- No UI changes, no template changes, no new features.

## Non-goals

- High-fidelity UI redesign.
- Trace Workbench replacement.
- MHTML export work.
- CSS refactoring.
- Harness structure changes.

## User Impact

Without this fix, clicking any session from the session list or dashboard leads to a 500 error page — the entire session detail feature is non-functional.

## Validation Strategy

1. **Unit smoke test**: A new pytest test that uses the Flask-style test client (or the actual `HTTPServer` with a mock fixture) to request a session detail URL and assert HTTP 200.
2. **Manual verification**: Start the server and curl a session detail URL, confirming HTTP 200 and the presence of key DOM markers (workbench, metrics strip, tab containers).
3. **Existing tests**: All 671 existing static/template tests must continue to pass.
