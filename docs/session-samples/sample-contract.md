# Session Sample Contract

This directory contains reference session samples used for cross-language validation of the normalization pipeline.

## Directory Structure

```
docs/session-samples/
├── claude-code/{session-id}/
│   ├── {session-id}.jsonl         # Input: Claude Code JSONL session file
│   ├── expected.normalized.jsonc  # Expected output: normalized artifact (JSONC with comments)
│   └── README.md                  # Session description
└── codex/{session-id}/
    ├── {session-id}.jsonl         # Input: Codex main thread JSONL
    ├── rollout-*.jsonl            # Input: Codex subagent rollout JSONL files
    ├── expected.normalized.jsonc  # Expected output: normalized artifact
    └── README.md                  # Session description
```

## File Roles

### Input Files (`.jsonl`)

- **Claude Code**: Single `.jsonl` file per session containing all events in chronological order.
- **Codex**: Main session `.jsonl` file plus zero or more `rollout-*.jsonl` subagent thread files.

### Expected Output (`expected.normalized.jsonc`)

The `expected.normalized.jsonc` file represents the canonical normalized artifact for a given session. It is written in JSONC format (JSON with comments) to document the purpose of each field.

- The file is the **source of truth** for what the normalization pipeline should produce.
- Comments (both `//` and `/* */`) are stripped before comparison.
- Field names and structure follow the normalized schema contract.

### Evidence-Only Files

- `litellm_calls/` directories (if present) contain LLM API call evidence used for manual review only. **Tests do not depend on these files.**
- `README.md` files provide human-readable session descriptions.

## Test Integration

The `SessionSampleIntegrationTest` (in `java/contract-tests`) drives the Java production pipeline against these samples:

1. **SourceAdapter.parse()** reads the `.jsonl` input files
2. **NormalizationEngine.normalize()** produces the normalized artifact
3. **CanonicalJsonWriter.serialize()** generates deterministic JSON output
4. The output is compared structurally against the stripped `expected.normalized.jsonc`

Any differences are recorded in `reports/session-sample-drift-report.md` with categorization:

| Category | Meaning |
|---|---|
| `production_bug` | Java output does not match expected; may indicate a bug in production code |
| `docs_stale` | Expected file may be outdated and need regeneration |
| `volatile_field` | Difference in timestamp, path, or other volatile field |
| `unknown` | Difference that cannot be automatically classified |
