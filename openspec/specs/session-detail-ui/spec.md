# Session Detail UI Spec

## Requirements

### Requirement: Single trace-first debug page

The session detail page SHALL provide a single Trace-first debugging experience as a stable, offline-capable debug page.

#### Scenario: Session summary display

The page SHALL display:
- Session title
- Agent name and model
- Start time and duration
- KPI metrics grouped into token analysis and call-count analysis
- Token analysis metrics: Tokens, Fresh, Cache R, Cache W, Output
- Call-count analysis metrics: Rounds, Tools, Failed, LLM Calls

#### Scenario: Issue summary display

The page SHALL display issue cards for:
- Failed rounds with aggregated failed tool call counts
- Highest token round

Issue cards SHALL be clickable buttons that jump to and expand the target round. When no issues exist, display "No actionable issues detected."

#### Scenario: Trace list

The page SHALL display a vertical list of all rounds. Each round SHALL show:
- Round number and status
- Summary/title text
- Tool count and failure count
- Token count
- Time

The first failed round SHALL be expanded by default; if no failures, expand R1.

#### Scenario: Trace controls

The page SHALL provide:
- All / Failed status filter
- Expand All / Collapse All buttons

#### Scenario: Inline round detail

When a round is expanded, it SHALL show:
- User prompt summary
- Assistant response summary
- LLM call span with token metrics
- Tool call spans with status and duration
- Failed tool error summaries
- Payload buttons only when payload data exists

#### Scenario: Payload modal

The page SHALL provide a modal dialog for viewing payloads with:
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
- `expand-all`
- `collapse-all`
- `open-payload`
- `payload-mode`
- `close-modal`
- `jump-round`
- `jump-anomaly`
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
- Token Usage collapsed chart, round bar chart, or hover tooltip

### Requirement: Global shell simplification

The global navigation for session detail SHALL be simplified. The Inspector panel SHALL NOT be rendered as a default third column on session detail pages.
