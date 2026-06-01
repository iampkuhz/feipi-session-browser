# Tasks: Fix Claude Usage Fragment Merge

Walk these tasks sequentially. Mark each checkbox with validation evidence when done.

## Phase 1: Parser Fix

- [x] 1.1 Preserve a whole Claude usage snapshot when merging same-message fragments.
  - Validation: `pytest tests/backend/test_claude_source.py` passed.

- [x] 1.2 Add regression coverage for same-message thinking/text/tool-use usage fragments.
  - Validation: `test_same_message_usage_fragments_keep_whole_provider_snapshot` asserts no per-field max mixing occurs.

- [x] 1.3 Run minimal relevant verification.
  - Validation: `pytest tests/backend/test_claude_source.py` passed; `pytest tests/backend/test_claude_source.py tests/test_llm_attribution_serializers.py -q` passed; `bash scripts/harness/doctor.sh` passed; `python3 scripts/harness/validate_openspec_layout.py` passed. `./scripts/session-browser.sh test` failed on pre-existing unrelated UI/index/test collection failures.
