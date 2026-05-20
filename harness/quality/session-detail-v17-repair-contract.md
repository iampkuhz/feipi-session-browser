# Session Detail v17 Complete Repair Contract

Scope: session detail only.

This is a complete execution package. It is not a patch package.

## Execution mode

All implementation tasks must be run as isolated foreground subagents, serially.

```text
single-threaded
one subagent at a time
fresh context per task
no background subagents
no parallel Task calls
no nested subagents
```

## CSS ownership

1. Canonical session-detail stylesheet:
   `src/session_browser/web/static/css/session-detail-timeline.css`

2. Merge required rules from:
   - `session-detail-timeline-v11.css`
   - `session-detail-response-blocks-v12.css`
   - any temporary `session-detail-payload-v16.css`
   - `seed-overlay/src/session_browser/web/static/css/session-detail-timeline-v17-canonical-patch.css`

3. After consolidation, session detail must not require:
   - `session-detail-timeline-v11.css`
   - `session-detail-response-blocks-v12.css`
   - `session-detail-payload-v16.css`

4. Prefer deletion if unused. At minimum, stop importing obsolete files and document them.

## Modal

All context/response/result/open payloads use the same centered floating modal:

```text
position: fixed
left/top 50%
transform translate(-50%, -50%)
width min(70vw, 1120px)
max-height 82vh
narrow width 92vw
body scrolls internally
backdrop visible
```

The modal must not replace the whole page. No `document.body.innerHTML`, no location navigation.

## Context payload

Context is the selected LLM call's model-input view.

It must include:

```text
relevant user input
all previous tool results that feed this LLM call
raw/reconstructed/partial source note
```

Consecutive tool results between two LLM calls must all appear in the next LLM call's context.

## Buttons

Every LLM call must have Context and Response buttons. Missing raw request means diagnostic payload, not missing button.

## Notes

No hardcoded note:

```text
仅捕获渲染上下文；完整 raw HTTP request 未持久化
```

Notes are generated from payload state or omitted.

## Tones

```text
complete/ok tool result -> muted/neutral
failed tool result -> red + useful excerpt
FAILED round status -> red/error tone
```

## Narrow screen

`.sd-round-preview__title` truncates and never invades `.sd-round-metric`, including `.sd-user-round`.
