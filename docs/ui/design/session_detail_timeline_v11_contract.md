# Session Detail Timeline v11 Contract

## Purpose

Fix the current session detail UI after v9:

1. Payload buttons must open a populated modal.
2. User input must be a first-class highlighted round.
3. Subagent sub-rounds must expand and show subagent LLM token usage, Context and Response.
4. `Collapse all` and `Expand all` must be one reversible button.
5. Design explanation text must not appear in the UI.

## Required DOM contracts

### Payload

Button:

```html
<button data-action="open-payload"
        data-payload-id="payload-r3-context"
        data-payload-title="R3 · Context">
  Context
</button>
```

Source:

```html
<template data-payload-source="payload-r3-context"
          data-payload-kind="context"
          data-payload-status="partial"
          data-payload-size="25.5K input">
  ...
</template>
```

Modal:

```html
<dialog id="payload-modal">
  <div class="sd-payload-modal__panel">
    <main data-payload-body>...</main>
  </div>
</dialog>
```

Rules:

- Every `open-payload` button must have `data-payload-id`.
- Every `data-payload-id` should match one `template[data-payload-source]`.
- If the source is missing, modal must show a Chinese diagnostic message.
- Modal body must never remain blank.

### Toggle all

Use one button:

```html
<button data-action="toggle-all" data-state="collapse">Collapse all</button>
```

Rules:

- If all visible rounds are open: text = `Collapse all`, state = `collapse`.
- If any visible round is closed: text = `Expand all`, state = `expand`.
- Click toggles all visible rounds and then refreshes the label.

### User input round

User input is rendered as a distinct round:

```html
<article class="sd-round sd-user-round"
         data-trace-round-row
         data-status="user">
```

It should not be hidden inside an LLM call.

### Subagent

Subagent is a nested mini session:

```text
Subagent
  SR1
    Sub LLM Call #1
      token metrics
      Context / Response
  SR2
    Bash / Read / pytest
  SR3
    Sub LLM Call #2
      token metrics
      Context / Response
```

Each sub-round is a disclosure:

```html
<button data-action="toggle-sub-round"
        aria-expanded="false"
        aria-controls="sub-round-...">
```

### Note logic

Do not render empty note blocks.

Use:

- `sd-note--ok`: full payload available.
- `sd-note--warn`: rendered context only; raw HTTP payload is missing.
- `sd-note--err`: payload id missing, source missing, parse failed, or button unmapped.
- `sd-note--info`: long content is truncated; modal has full content.

## Forbidden visible UI text

Do not place design explanations in the page body:

- `Round 内按时间顺序纵向推进`
- `用户输入作为独立高亮 round`
- `payload modal 必须可打开`
- `sd-note 展示规则`

These belong in docs or tests, not in the product UI.
