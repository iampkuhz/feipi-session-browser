# HIFI Visual Test Fixture Session

Deterministic fixture session for Playwright and visual regression tests.

## Structure

```
session_hifi_fixture/
├── history.jsonl                          # Claude Code history index (1 entry)
└── projects/
    └── test-hifi-project/
        └── hifi-viz-session-001.jsonl     # Full conversation event stream
```

## Session Profile

- **Agent:** claude_code
- **Session ID:** hifi-viz-session-001
- **Project:** test-hifi-project
- **Model:** claude-sonnet-4-20250514

### Conversation Flow (7 rounds)

1. **Round 1:** User asks about token visualization. Assistant responds with exploration plan.
2. **Round 2:** Assistant explores codebase with LS + Read tools.
3. **Round 3:** Assistant reads metrics.py to understand token data pipeline.
4. **Round 4:** Assistant invokes Explore subagent (fails with API 401 key_model_access_denied).
5. **Round 5:** Assistant reads CSS directly after subagent failure, finds token bar styles.
6. **Round 6:** Assistant creates template, runs tests (first Bash fails: `python3: command not found`).
7. **Round 7:** Assistant re-runs tests with full path, presents implementation summary.

### Signals Present

| Signal | Details |
|--------|---------|
| Rounds | 7 conversation rounds |
| Tool types | LS, Read, Agent, Write, Bash (5 types) |
| Failed tools | 2 -- Agent (API 401) + Bash (command not found) |
| Token usage | input=60,400, output=875, cache_read=45,500, cache_write=22,000 |
| Subagent | 1 Explore agent call (failed) |
| Anomaly | Failed tool signals, cache growth across rounds |
| Token growth | Cache read grows from 0 to 14,500 across rounds |

### Token Summary (session-level)

- Input tokens: 60,400
- Output tokens: 875
- Cache read: 45,500
- Cache write: 22,000

## Usage

### In pytest

```python
def test_something(self, hifi_fixture_session):
    base_url, agent, session_id = hifi_fixture_session
    url = f"{base_url}/sessions/{agent}/{session_id}"
    # ... test against url
```

### Direct parsing

```python
from session_browser.sources.claude import parse_session_detail
summary, messages, tool_calls, subagent_runs = parse_session_detail(
    "test-hifi-project", "hifi-viz-session-001"
)
```

### With Playwright

The fixture session is served on port 18902 by the `hifi_fixture_session` fixture.
Use this URL for Playwright visual tests:

```javascript
// tests/playwright/session-detail.spec.js
const baseURL = process.env.HIFFI_FIXTURE_URL || "http://127.0.0.1:18902";
await page.goto(`${baseURL}/sessions/claude_code/hifi-viz-session-001`);
```

## Maintenance

When modifying the fixture JSONL:
1. Keep the event format consistent with Claude Code's native `.jsonl` structure.
2. Ensure each assistant message has a unique `message.id`.
3. Tool results in user events must reference the matching `tool_use_id`.
4. Update the token summary table above if totals change.
