# Spec: Claude Usage Fragment Merge

## Requirement: Whole Snapshot Usage Merge

When Claude Code emits multiple JSONL fragments for the same assistant message id, token usage must be derived from one whole provider usage snapshot rather than field-wise maxima across fragments.

### Scenario: Tool-use fragment carries final cache-aware usage

- **Given** one assistant message id appears in thinking/text fragments with high `input_tokens` and a later tool-use fragment with `cache_read_input_tokens`, `cache_creation_input_tokens`, and `output_tokens`
- **When** the Claude source parser extracts the logical assistant message
- **Then** the parsed usage SHALL match one raw usage snapshot
- **And** the parsed usage SHALL NOT combine `input_tokens` from the thinking/text fragment with cache fields from the tool-use fragment
