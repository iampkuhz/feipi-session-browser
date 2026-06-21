# Spec: 修正 Codex Token Mass 归因恢复

## Requirement: Codex call extraction SHALL treat runtime outputs as later request inputs

Codex extraction SHALL classify typed items by their intrinsic shape before assigning call occurrence through the extraction state machine.

### Scenario: tool_search_output is consumed by the next call

- **Given** a Codex call emits `response_item.tool_search_call` with call id `call_X`
- **And** a later `response_item.tool_search_output` appears before the closing `token_count`
- **When** the call is closed and the next call snapshot is frozen
- **Then** the first call's response SHALL include `call_X` in `response.tool_call_ids`
- **And** the next call's request SHALL include `call_X` in `request.tool_result_ids`
- **And** the tool execution for `call_X` SHALL have `result_consumed_by_call_id` set to the next call id.

### Scenario: subagent model uses turn model

- **Given** a Codex subagent rollout has `session_meta.model_provider` and `turn_context.model`
- **When** normalized calls are emitted
- **Then** each subagent call model SHALL prefer `turn_context.model`
- **And** `model_provider` MAY remain provenance but SHALL NOT overwrite the call model.

## Requirement: Codex source attribution SHALL distinguish occurrence coverage from token mass

Codex source units SHALL prove visible occurrences, content, order, and evidence level. They SHALL NOT be scaled into provider token mass unless provider supplies source-level token evidence.

### Scenario: request candidates do not fabricate per-candidate tokens

- **Given** a Codex call has provider-reported `fresh_input_tokens`
- **And** normalized request source units for `user_input`, `tool_results`, or `conversation_history`
- **When** request accounting attribution is built
- **Then** `fresh_input_tokens.tokens` SHALL equal provider-reported fresh input
- **And** candidate entries SHALL carry source/evidence metadata with `token_status=unknown_mass`
- **And** `candidate_total_tokens` SHALL NOT be forced to equal the provider fresh input
- **And** `unattributed_tokens` SHALL retain the unresolved provider serialization or hidden context residual.

### Scenario: cache read remains an accounting field

- **Given** Codex usage reports `cached_input_tokens`
- **When** attribution payload is built
- **Then** `cache_read_tokens` SHALL expose provider accounting
- **And** no request candidate SHALL be created solely to explain provider cache read
- **And** cache read SHALL NOT be assigned to a specific source without cache-span evidence.

### Scenario: response lanes do not imply per-item token splits

- **Given** a Codex response contains multiple non-reasoning output lanes
- **And** provider usage only reports aggregate `output_tokens` and optional `reasoning_output_tokens`
- **When** response accounting attribution is built
- **Then** `reasoning_output_tokens` MAY be shown as provider aggregate when available
- **And** non-reasoning candidates SHALL be listed as content occurrences without claiming exact per-item token splits.
