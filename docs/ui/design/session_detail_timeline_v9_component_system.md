# Session Detail Timeline v9 Component System

## Direction

The session detail page is Trace-first. Do not add a right-side inspector or independent Calls/Hotspots tabs.

The round detail is a vertical timeline because it represents historical execution order:

```text
LLM Call
Tool batch
LLM Call
Subagent block
```

Parallel tools remain vertically listed, but are grouped inside one `Tool batch` container.

## Component primitives

### Button

Class:

```text
.sd-btn
.sd-btn--sm | .sd-btn--md
.sd-btn--primary | .sd-btn--secondary
```

Default heights:

```text
sm: 28px
md: 30px
```

### Pill

Class:

```text
.sd-pill
.sd-pill--model | .sd-pill--main | .sd-pill--ok | .sd-pill--err
```

Use for model, lane, status, and summary tags.

### Metric cell

Class:

```text
.sd-mcell
```

Contract:

```text
label = small uppercase, muted
value = large mono, dark, heavy
```

### Timeline

Class:

```text
.sd-timeline
.sd-timeline-item
.sd-timeline-dot
```

The vertical line is owned by `.sd-timeline:before`.

### LLM call

Class:

```text
.sd-card.sd-llm-card
[data-inline-call-card]
```

Contains header, metric cells, and compact payload line.

### Tool batch

Class:

```text
.sd-tool-group
.sd-tool-row
```

Parallel tool calls are grouped as one batch. Tool rows are still vertical.

### Subagent

Class:

```text
.sd-subagent
.sd-sub-round
.sd-sub-step
```

Subagent is rendered as a nested mini session, not a full duplicate of the main page.

## Subagent model

Use this semantic mapping:

```text
Main Round = primary session round
Subagent Block = delegated task inside a main round
Sub-round = derived mini round if subagent internal events are available
```

If logs contain subagent internal events, render `SR1 / SR2 / SR3`. If logs only contain a summary, render one compact `Subagent Result` block.

## Button policy

Allowed visible buttons:

```text
All
Failed
Collapse all
Context
Response
Result
Close
Rendered
Raw
```

Avoid:

```text
Map
Inspector
Focus
Calls
Hotspots
Open selected
High token
Go
Clear
```
