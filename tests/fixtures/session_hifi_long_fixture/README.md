# Long Session Fixture (100 Rounds)

Synthetic 100-round session for performance testing and trace rendering validation.

## Structure

```
session_hifi_long_fixture/
├── history.jsonl                           # Claude Code history index (1 entry)
├── gen_fixture.py                          # Script to regenerate the fixture
└── projects/
    └── test-hifi-project/
        └── long-session-001.jsonl          # 100-round conversation event stream (~300 lines)
```

## Session Profile

- **Agent:** claude_code
- **Session ID:** long-session-001
- **Project:** test-hifi-project
- **Model:** claude-sonnet-4-20250514
- **Rounds:** 100 conversation rounds

### Characteristics

- Each round has 1-2 LLM calls with varying tool usage
- Mix of tool types: Read, Write, Bash, LS, Grep, Edit, Agent, Find
- Cache tokens present in early rounds (rounds 1-20)
- Some rounds have 2 LLM calls (tool-use + final response)
- Varied token counts (500-5000 input, 50-500 output per call)

## Usage

### In pytest

```python
def test_long_session(self, long_fixture_session):
    base_url, agent, session_id = long_fixture_session
    url = f"{base_url}/sessions/{agent}/{session_id}"
    # ... test against url
```

### Regenerate fixture

```bash
python3 tests/fixtures/session_hifi_long_fixture/gen_fixture.py
```

## Maintenance

The fixture is deterministic and can be regenerated at any time from `gen_fixture.py`.
If you need different characteristics (more rounds, different tool mix, etc.),
modify the generator script and re-run it.
