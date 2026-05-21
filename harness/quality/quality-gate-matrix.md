# Quality Gate Matrix

| 改动类型 | 必跑 deterministic gates | Stop hook enforcement | LLM diagnostic |
|---|---|---|---|
| UI CSS | static CSS + browser layout + pytest | required PASS artifact | optional |
| UI template | template contract + browser layout + pytest | required PASS artifact | optional |
| UI JS | browser interaction/layout gate + pytest | required PASS artifact | optional |
| hook scripts | hook self-test + pytest | required PASS artifact | optional |
| quality scripts | self-test + pytest | required PASS artifact | optional |
| docs only | no browser gate | no UI gate | optional |
| openspec only | openspec validators | existing harness gate | optional |

## Gate Scripts

| Gate | Script |
|---|---|
| static CSS | `scripts/quality/check_session_detail_static.py` |
| template contract | `tests/test_session_detail_layout_contract.py` (pytest) |
| browser layout | `scripts/quality/run_session_detail_layout_gate.py` |
| pytest suite | `./scripts/session-browser.sh test` |
| quality runner | `scripts/quality/run_quality_gate.py --target session-detail` |
| stop enforcement | `scripts/hooks/stop_quality_gate.py` |
| LLM diagnostic | `.claude/commands/diagnose-ui-gate.md` |

## Artifact Paths

- `tmp/quality/<change-id>/quality-gate-summary.json` — unified summary
- `tmp/quality/<change-id>/session-detail-layout-result.json` — browser metrics
- `tmp/quality/<change-id>/session-detail-layout-1440.png` — screenshot
- `tmp/changed-files.jsonl` — changed file log (read by stop hook)
