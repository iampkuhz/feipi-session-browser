# Design: Fix Session Detail Runtime

## Current Runtime Path

1. **Entry**: `python -m session_browser serve` → `cli.py:cmd_serve()` → `routes.py:create_server()`
2. **Route**: `GET /sessions/<agent>/<session_id>` → `SessionBrowserHandler._serve_session()`
3. **Template**: `session.html` (extends `base.html`)
4. **Static assets**: `/static/style.css`, `/static/js/*.js` served by `_serve_static()`

## Suspected Failure Modes

### 1. `ConversationRound.title` AttributeError (CONFIRMED)

**Location**: `src/session_browser/web/routes.py:1491`

```python
session_rounds=[
    {"idx": i + 1, "name": r.title or f"Round {i + 1}",
     "status": getattr(r, "status", ""), "is_current": False}
    for i, r in enumerate(rounds)
],
```

`ConversationRound` (models.py:222) has these fields:
- `user_msg`, `assistant_msg`, `tool_calls`, `total_tokens`, `token_ratio`
- `round_index`, `llm_call_count`, `llm_error_count`, `interactions`
- `preview_text`

It does **not** have a `title` field. The template side-bar uses `session_rounds[].name` for the round map labels, so the fix is to use `r.preview_text` instead of `r.title`.

**Evidence**: `curl` to a session detail URL returns HTTP 500 with body containing:
```
'ConversationRound' object has no attribute 'title'
```

### 2. `conftest.py` passes `--db` flag that CLI doesn't accept (KNOWN, NOT BLOCKING)

The `live_server_url` fixture in `tests/conftest.py` starts the server with `--db <path>`, but `cli.py` doesn't accept `--db`. This fixture is currently non-functional, but all existing tests are static/template-only and don't use `live_server_url`. This is documented as future work.

### 3. Static asset loading

Static assets are served correctly — confirmed by dashboard page working. No issue here.

### 4. Jinja template rendering

The template itself is structurally sound (671 static tests pass). The failure happens before template rendering, during context construction in the route handler.

## Minimal Fix Strategy

**One-line change**: Replace `r.title` with `r.preview_text` in `routes.py:1491`.

This is the minimal fix because:
- `preview_text` is already computed for each round (via `round.compute_preview()` called at line 1436).
- It serves the same purpose: a short human-readable label for the round map sidebar.
- Adding a `title` property to `ConversationRound` that aliases `preview_text` would be more future-proof but adds code for no functional benefit right now.

**Decision**: Use `r.preview_text` directly — simplest, least surface area.

### Additional: Add a route-level smoke test

Create `tests/test_session_detail_route.py` that:
1. Uses Python's `http.server` test utilities to start a server on a random port.
2. Requests `/sessions/<agent>/<session_id>`.
3. Asserts HTTP 200.
4. Asserts response contains `wb-head` and `metrics-strip-card`.

Since there's no real test database with fixture sessions, the test will use the `--allow-empty` flag and a minimal in-memory approach, or skip if `SB_TEST_DB` is not set.

## Risks

- **`preview_text` might be empty**: The template already handles empty names via the Jinja fallback in `session.html` (the round map shows "Round N" if the name is empty). Actually, looking at the template more carefully, the sidebar uses `{{ round.name | truncate(28) }}` — if `preview_text` is empty, the sidebar will show an empty string. The fix should keep the `or f"Round {i + 1}"` fallback, which it already has.

- **Other round attributes**: The `session_rounds` dict also accesses `getattr(r, "status", "")`. `ConversationRound` doesn't have a `status` field either, but `getattr` with a default makes this safe. No change needed.

## Rollback Plan

Revert the one-line change in `routes.py`. The session detail page will return to HTTP 500, but no data is modified.

## Validation Commands

```bash
# Fix verification
curl -fsS -o /dev/null -w "%{http_code}" http://127.0.0.1:18999/sessions/claude_code/<id>
# Expected: 200

# Regression tests
python -m pytest tests/ -v
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/validate_harness_structure.py
```
