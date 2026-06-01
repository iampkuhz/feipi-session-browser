# Proposal: Fix Claude Usage Fragment Merge

## Problem

Claude Code can persist one assistant response as multiple JSONL fragments with the same message id. The current parser merges usage by taking the maximum per token field, which can combine fields from different fragments and create a token total that never existed in the raw log.

## Scope

- Change Claude Code usage parsing to keep token fields from one provider usage snapshot.
- Add regression coverage for thinking/text fragments followed by a tool-use fragment with cache fields.
- Keep attribution UI formulas unchanged.

## Non-goals

- Do not change Codex or Qoder usage normalization.
- Do not reinterpret provider cache-read semantics across sessions.
- Do not redesign attribution buckets.

## User impact

Request attribution and session totals no longer overstate a single LLM call by mixing fresh input from one fragment with cache fields from another.

## Validation strategy

- Run the focused Claude source parser tests.
- Run the session-browser test command if practical after the focused fix passes.
