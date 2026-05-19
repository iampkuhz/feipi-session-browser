# Session Detail Payload Contracts v15

## Core rule

`Context`, `Response`, and `Result` buttons do not show the same content.

## Context button

Context means the effective model input view. It must show:

```text
1. User input
2. Tool result list before this LLM call
3. Optional warning when raw HTTP request was not persisted
```

Data sources:

```text
current round user message
tool_result/tool call records that occurred before the selected LLM call
raw/reconstructed context if available
```

## Response button

Response means assistant output from the selected LLM call. It must show ordered content blocks:

```text
text
tool_use / tool command list
```

Data sources:

```text
LLMCall response content blocks
normalized assistant message parts
tool_use name/id/input
```

## Result button

Result means one selected tool result only. It must show:

```text
tool id
tool kind
status / exit code
command or input
output / stderr / error summary
```

Data sources:

```text
selected ToolCall / tool_result record
```

## Empty state is forbidden

If a payload source is missing, the modal must show a diagnostic block, not a blank panel.
