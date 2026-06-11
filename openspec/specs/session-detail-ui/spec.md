# Session Detail UI Spec

## Requirements

### Requirement: Single trace-first debug page

The session detail page SHALL provide a run-analysis experience as a stable, offline-capable debug page. The first viewport SHALL summarize run health, token cost, cache health, workload, and active time. Trace and Payload SHALL remain drill-down workspaces.

#### Scenario: Session summary display

The page SHALL display:
- Session title
- Agent name, model, project, created/updated timestamps, session id, and the indexed local session file path when available
- Exactly five primary KPI cards: Run Health, Total Tokens, Cache Health, Workload, Active Time
- Run Health secondary metrics: Issue Rounds, Failed Tools, Payload Gaps, Attribution Gaps
- Total Tokens secondary metrics: Fresh, Cache Read, Cache Write, Output
- Cache Health secondary metrics: Input-side Tokens, Low-cache Rounds, Fresh Spike Rounds
- Workload secondary metrics: Main Calls, Subagent Calls, Tool Calls, Subagent Runs
- Active Time secondary metrics: Duration, Waiting Time, Model Time, Tool Time

Each primary KPI card SHALL render no more than four secondary KPI values.

The Hero SHALL display the local session file path as a `Session file` row when the index or parser has resolved a JSONL source path. The row SHALL expose a copy button with `data-action="copy"` and `data-copy-text` set to the full path. If no file path is known, the row SHALL be omitted.

#### Scenario: Token component extraction

Token metrics SHALL use exactly five component fields:
- Fresh: provider-reported request input size for the call
- Cache Read: provider-reported cache read input tokens
- Cache Write: provider-reported cache creation/write input tokens
- Output: provider-reported visible output tokens
- Total: Fresh + Cache Read + Cache Write + Output

Fresh SHALL NOT subtract Cache Read or Cache Write. When one logical LLM call has multiple usage fragments, Fresh SHALL come from the largest non-zero request input snapshot, while Cache Read, Cache Write, and Output SHALL come from one final accounting snapshot.

#### Scenario: Analysis cards display

The page SHALL display analysis cards for:
- Token Timeline + Cache Health
- Top Cost Drivers
- Call Cost Distribution
- Tool Impact
- Subagent Breakdown
- Issues & Repro Seeds
- Payload Coverage
- Context Budget

Token Timeline + Cache Health and Context Budget SHALL span the full analysis grid width on desktop. Other analysis cards SHALL use the two-column grid on desktop and single-column layout on narrow screens.

#### Scenario: Issue summary display

The page SHALL display issue cards for:
- Failed rounds with aggregated failed tool call counts
- Highest token round

Issue cards SHALL be clickable buttons that jump to and expand the target round. When no issues exist, display "No actionable issues detected." The Hero issue strip SHALL NOT display "No issues found" when any tool failure, LLM error, payload gap, or attribution error exists.

#### Scenario: Trace list

The page SHALL display a vertical list of all rounds. Each round SHALL show:
- Round number and status
- Summary/title text
- Tool count and failure count
- Token count
- Time
- Signals: Failed, Subagent, Payload Gap, Attribution Gap

The first failed round SHALL be expanded by default; if no failures, expand R1.

#### Scenario: Trace controls

The page SHALL provide:
- All / Failed status filter
- Expand All / Collapse All buttons

The Failed filter SHALL show failed rounds and rounds containing any failure signal. The filter state SHALL be reflected in `trace_status` URL parameter. Selected round and selected tab SHALL be reflected in `round` and `tab` URL parameters.

#### Scenario: Inline round detail

When a round is expanded, it SHALL show:
- User prompt summary
- Assistant response summary
- LLM call span with token metrics
- Tool call spans with status and duration
- Failed tool error summaries
- Payload buttons only when payload data exists

#### Scenario: Payload tab and modal

The page SHALL provide a persistent Payload tab with:
- Left call selector with All / Failed / Missing / Error filters
- Right selected call detail
- Detail sections in this fixed order: Overview, Request Attribution, Response Attribution, Raw Request, Raw Response, Related Results

The selector SHALL keep an internal scroll area on desktop and narrow screens. Selecting a coverage matrix cell SHALL switch to the Payload tab, apply the corresponding selector filter, and select the first matching failed/missing/error call.

The page SHALL also provide a modal dialog for viewing payloads with:
- View Request / View Response / View Result buttons
- Rendered / Raw display mode toggle
- Multi-part segmented display
- Close via backdrop click, Escape key, or close button

#### Scenario: MHTML self-contained export

MHTML export SHALL produce self-contained HTML with inline CSS and JS. The exported page SHALL preserve all interactions when opened offline. No external network requests SHALL be required.

### Requirement: ARIA accessibility for trace rows

Each trace row SHALL be a semantic `<button type="button">` element with:
- `aria-expanded` reflecting the current expanded state ("true" or "false")
- `aria-controls` referencing the associated trace-detail element ID
- The trace-detail element SHALL have an `id` matching the `aria-controls` value

### Requirement: Payload buttons on spans

LLM call spans and tool call spans SHALL render a "Payload" button when payload data exists. The button SHALL have:
- `data-action="open-payload"` attribute
- `data-payload-key` referencing a key in `window.__SESSION_PAYLOADS__`

### Requirement: Shell residue gate

The session detail page SHALL NOT render:
- Sidebar Round Map (the `.round-map` section)
- Projects / Agents navigation links in sidebar
- Topbar shell toggle buttons (sidebar toggle ☰, right panel toggle ☰, focus ●)
- Map / Inspector / Focus layout mode buttons
- Density toggle button
- Visible disabled placeholder buttons (search, export, theme)

### Requirement: No content-modal entry points

The page SHALL NOT render a `content-modal` element or any `data-content-modal` buttons. The `openContentModal` function SHALL NOT be defined.

### Requirement: Dead button gate

Every visible `<button>` on the session detail page SHALL have a supported `data-action` value from this list:
- `status-all`
- `status-failed`
- `toggle-all`
- `toggle-round`
- `open-payload`
- `open-payload-tab`
- `open-trace-step`
- `select-payload-call`
- `payload-filter`
- `payload-mode`
- `close-modal`
- `close-payload`
- `copy`
- `jump-round`
- `jump-anomaly`
- `retry-attribution`
- `retry-round`
- `md-toggle` (tool result markdown toggle)

### Requirement: No removed entries

The session detail page SHALL NOT render:
- Calls tab, Hotspots tab, or workbench view switching
- Resident Inspector panel as a default session detail entry
- Round Map
- Map / Inspector / Focus layout mode buttons
- Density toggle button
- Visible disabled placeholder buttons (search, export, theme)
- Failed only / High token / Open selected chips
- Message / Tool / Error type filters
- Timeline jump input and Go button
- × Clear filter button
- Independent Calls tab/table
- Independent Hotspots tab/cards
- Legacy Token Usage collapsed chart

### Requirement: Global shell simplification

The global navigation for session detail SHALL be simplified. The Inspector panel SHALL NOT be rendered as a default third column on session detail pages.
