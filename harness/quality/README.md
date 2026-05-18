# Quality Gates

Deterministic validation before success reports.
LLM diagnostics are optional/on-demand and must not be wired into hooks.
Runtime artifacts live under `.agent/quality/<change-id>/` and are not source docs.

## Structure

| File | Purpose |
|---|---|
| [quality-gate-matrix.md](./quality-gate-matrix.md) | Which gates run for which change types |
| [ui-layout-contract.md](./ui-layout-contract.md) | Session detail layout hard metrics |
| [ui-gate-diagnostic.md](./ui-gate-diagnostic.md) | On-demand LLM diagnostic boundary |
| [gates.yaml](./gates.yaml) | Harness gate configuration |
| [gates.md](./gates.md) | Gate definitions and status |

## Running Gates

```bash
# Unified runner
python3 scripts/quality/run_quality_gate.py --target session-detail

# Individual gates
python3 scripts/quality/check_session_detail_static.py
python3 -m pytest tests/test_session_detail_layout_contract.py
python3 scripts/quality/run_session_detail_layout_gate.py --url ...

# Stop hook enforcement
python3 scripts/hooks/stop_quality_gate.py
```

## On-Demand LLM Diagnostic

```
/diagnose-ui-gate
```

This reads failed gate artifacts and suggests minimal fixes. It is NOT a gate — it cannot pass or block a stop hook.
