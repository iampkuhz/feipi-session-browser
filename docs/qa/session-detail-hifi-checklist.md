# Session Detail HiFi Layout — Manual QA Checklist

> **Change:** `align-session-detail-hifi-layout-quality`
> **Reviewer:** [name]
> **Date:** [YYYY-MM-DD]
> **Baseline commit:** [git SHA]
> **Screenshots:** `test-results/screenshots/`

## How to use

1. Start the local server: `./scripts/session-browser.sh serve`
2. Open `http://localhost:18999/session/93ecbcf2` (or any session with rich data).
3. Walk each section below; mark **PASS / FAIL / N/A**.
4. For FAIL items, note the symptom, expected behavior, and a screenshot filename.
5. Run automated QA scripts (listed at the bottom) to complement manual review.
6. Fill in the Self-Assessment section before merging.

---

## 1. Hero Section

| # | Check | Status | Notes |
|---|-------|--------|-------|
| H-1 | Session title is visible and truncated gracefully (ellipsis, not wrap) | | |
| H-2 | KPI cards render with consistent spacing and alignment (e.g., tokens, cost, latency) | | |
| H-3 | Anomaly banner (if session has anomalies) appears directly below title, with correct icon and color | | |
| H-4 | Meta chips (model, provider, timestamp) are horizontally aligned and use consistent chip styling | | |
| H-5 | Secondary metrics (if present) use smaller font and muted color — not competing with KPI cards | | |
| H-6 | Hero section does not cause vertical gap overflow on narrow viewports | | |

**Expected selectors:** `[data-session-overview-hero]`, `.hero`, `.hero-alerts`, `.anomaly-banner`

---

## 2. Workbench Container

| # | Check | Status | Notes |
|---|-------|--------|-------|
| W-1 | Workbench container (`.card.wb` / `[data-workbench]`) exists and is visually distinct | | |
| W-2 | Header buttons (Export, Jump, Inspect) are in the workbench head, not duplicated in hero | | |
| W-3 | View switch buttons (Trace / Calls / Hotspots) are present and styled consistently | | |
| W-4 | Active view button has a clear visual indicator (background, border, or underline) | | |
| W-5 | Workbench sits below hero without excessive whitespace gap | | |

**Expected selectors:** `[data-workbench]`, `.wb-viewbar`, `.view-switch`, `[data-switch]`

---

## 3. Trace View

| # | Check | Status | Notes |
|---|-------|--------|-------|
| T-1 | Span rows are compact (single-line, no excessive vertical padding) | | |
| T-2 | Expand/collapse toggle is round and visually distinct | | |
| T-3 | Span list is scrollable within its container — does not push footer off-screen | | |
| T-4 | Badges (role, status, tool) are small, inline, and color-coded consistently | | |
| T-5 | Filter bar (if present) is sticky or clearly separated from span list | | |
| T-6 | Clicking a span row opens the inspector with contextual content | | |

**Expected selectors:** `[data-view="trace"]`, `.trace-span-list`, `.trace-filter-bar`

---

## 4. Calls View

| # | Check | Status | Notes |
|---|-------|--------|-------|
| C-1 | Table structure is clear: columns for role, tokens, status, latency | | |
| C-2 | Payload preview is visible or expandable per row | | |
| C-3 | Inspector trigger (click row) opens relevant call context in inspector | | |
| C-4 | Table header is sticky on scroll | | |
| C-5 | Empty state shows a helpful message (no blank panel) | | |

**Expected selectors:** `[data-view="calls"]`, `.calls-table`

---

## 5. Hotspots View

| # | Check | Status | Notes |
|---|-------|--------|-------|
| Ht-1 | Diagnostic cards render with title, severity icon, and description | | |
| Ht-2 | Failure hotspots are visually distinct (red/orange border or background) | | |
| Ht-3 | Payload hotspots show truncated content with click-to-expand | | |
| Ht-4 | Cost hotspots highlight the expensive spans/calls clearly | | |
| Ht-5 | Click-to-jump navigates to the corresponding span/call in Trace/Calls view | | |
| Ht-6 | Empty state shows a "no issues" confirmation | | |

**Expected selectors:** `[data-view="hotspots"]`, `.hotspots-diagnostic`, `.hotspot-item`

---

## 6. Inspector Panel

| # | Check | Status | Notes |
|---|-------|--------|-------|
| I-1 | Inspector shows contextual content based on selected span/call | | |
| I-2 | Round view displays turn-level summary (prompt, response, tokens) | | |
| I-3 | LLM view shows model, provider, and raw response details | | |
| I-4 | Tool call view shows tool name, arguments, and result | | |
| I-5 | Tab switching is smooth with no layout shift | | |
| I-6 | Inspector can be closed (Esc or close button) without affecting main view | | |

**Expected selectors:** `[data-context-inspector]`, `.inspector`, `.inspector-inner`, `.insp-title`

---

## 7. Full Payload Viewer

| # | Check | Status | Notes |
|---|-------|--------|-------|
| P-1 | JSON mode renders with syntax highlighting and indentation | | |
| P-2 | Rendered mode shows human-readable content (markdown, tool output) | | |
| P-3 | Raw mode shows unprocessed text | | |
| P-4 | Diff mode (if available) highlights additions/removals | | |
| P-5 | Fallback for non-JSON payloads shows raw text with a note | | |
| P-6 | Viewer is dismissible without affecting session view | | |

**Expected selectors:** `.payload-viewer`, `.payload-mode-tabs`

---

## 8. Token Charts Card Placement

| # | Check | Status | Notes |
|---|-------|--------|-------|
| TC-1 | `token-charts-card` is **NOT** a dominant first-screen block between hero and workbench | | |
| TC-2 | `token-charts-card__body` is inside the workbench (or removed entirely per HIFI target) | | |
| TC-3 | `token-charts-card__body` is **NOT** inside `data-view="trace"` (Trace view primary area) | | |
| TC-4 | If rendered, card height does not exceed 400px (inline style or content) | | |
| TC-5 | Token diagnostics are available in Hotspots or inspector as alternate views | | |

**Automated check:** `python3 scripts/qa/session_ui/check_token_charts_card_layout.py`

---

## 9. Long Session Behavior

| # | Check | Status | Notes |
|---|-------|--------|-------|
| L-1 | Scrolling through a long session (50+ spans) is smooth — no jank or freeze | | |
| L-2 | No layout drift: header, workbench boundary, and inspector position remain stable | | |
| L-3 | Virtual scrolling or lazy rendering is used if applicable | | |
| L-4 | Memory usage remains reasonable (no runaway DOM growth) | | |

**Screenshot reference:** `test-results/screenshots/long-session-trace.png`

---

## 10. Keyboard Shortcuts

| # | Check | Status | Notes |
|---|-------|--------|-------|
| K-1 | `j` / `k` — navigate up/down through list items (spans, calls) | | |
| K-2 | `Enter` — open selected item in inspector | | |
| K-3 | `Esc` — close inspector or payload viewer | | |
| K-4 | `/` — focus filter/search bar | | |
| K-5 | `t` / `c` / `h` — switch to Trace / Calls / Hotspots view | | |
| K-6 | `i` — toggle inspector open/close | | |

---

## 11. Layout Modes

| # | Check | Status | Notes |
|---|-------|--------|-------|
| M-1 | **Map mode** — shows session overview with span/call map, no inspector | | |
| M-2 | **Inspector mode** — side-by-side main view + inspector panel | | |
| M-3 | **Focus mode** — single-panel, maximized content area | | |
| M-4 | Mode switching preserves scroll position and selection state | | |

**Screenshot references:** `test-results/screenshots/inspector-closed.png`, `test-results/screenshots/inspector-open.png`

---

## 12. CSS Quality

| # | Check | Status | Notes |
|---|-------|--------|-------|
| C-1 | Text contrast meets WCAG AA (4.5:1) — no gray-on-gray that is hard to read | | |
| C-2 | Font sizes are consistent across sections (body ~14px, headings ~16-18px, labels ~12px) | | |
| C-3 | Button styles are consistent: same border-radius, padding, hover state across all zones | | |
| C-4 | No inline style overrides that duplicate CSS rules | | |
| C-5 | Dark mode (if applicable) does not break any of the above | | |

---

## Automated QA Scripts

Run these before and after your change to compare results:

```bash
# Main layout quality scoring (hero, workbench, token chart, legacy tabs, inspector, overflow, button roles)
python3 scripts/qa/session_ui/check_layout_quality.py

# Token charts card placement verification
python3 scripts/qa/session_ui/check_token_charts_card_layout.py
```

Both scripts exit non-zero on FAIL. They operate on either a running local server (default `http://localhost:18999/session/93ecbcf2`) or a baseline HTML file.

---

## Screenshot Reference

| File | Description |
|------|-------------|
| `session-detail-overview.png` | Full session detail overview page |
| `session-detail-trace.png` | Trace view with span list |
| `session-detail-calls.png` | Calls view with table |
| `session-detail-hotspots.png` | Hotspots view with diagnostic cards |
| `inspector-closed.png` | Session with inspector panel closed |
| `inspector-open.png` | Session with inspector panel open |
| `long-session-trace.png` | Long session scroll test |
| `token-placement.png` | Token charts card placement verification |
| `metrics-strip-fullpage.png` | Full-page metrics strip |

---

## Self-Assessment

> Fill this out after completing the manual review and before merging.

### Overall verdict

- **Status:** PASS / FAIL
- **Quality score:** __/12 sections passed

### Section results

| Section | Status | Key findings |
|---------|--------|-------------|
| 1. Hero Section | | |
| 2. Workbench | | |
| 3. Trace View | | |
| 4. Calls View | | |
| 5. Hotspots View | | |
| 6. Inspector | | |
| 7. Payload Viewer | | |
| 8. Token Charts | | |
| 9. Long Session | | |
| 10. Shortcuts | | |
| 11. Layout Modes | | |
| 12. CSS Quality | | |

### Automated QA results

```
check_layout_quality.py:       PASS / FAIL  (score: __%)
check_token_charts_card_layout.py: PASS / FAIL
```

### Changed area summary

- **What changed:**
- **Why:**
- **Risk level:** Low / Medium / High

### Known visual regressions

1. _(none / describe)_
2.
3.

### Follow-up items

1. _(none / describe)_
2.
3.

### Reviewer sign-off

- **Reviewed by:**
- **Date:**
- **Comments:**
