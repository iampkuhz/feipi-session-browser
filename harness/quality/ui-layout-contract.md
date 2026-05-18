# UI Layout Contract: Session Detail

## Hard Metrics (1440x1100 viewport)

These thresholds are **deterministic** — they come from `getComputedStyle` / `getBoundingClientRect`,
not subjective screenshot comparison.

| Metric | Threshold | Failure Code |
|---|---|---|
| `scrollOk` | `scrollWidth <= viewportWidth + 2` | `HORIZONTAL_SCROLL` |
| `shellGrid` | must NOT start with `0px` | `SHELL_ZERO_COLUMN` |
| `main.width` | >= 1200px | `MAIN_WIDTH_TOO_SMALL` |
| `detail.width` (.session-detail-phase1) | >= 1100px | `DETAIL_WIDTH_TOO_SMALL` |
| `hero.width` | >= 900px | `HERO_WIDTH_TOO_SMALL` |
| `titleBeforeKpis` | `title.bottom <= kpis.top + 4` | `TITLE_OVERLAPS_KPIS` |
| `title.height` | <= 180px | `TITLE_TOO_TALL` |

## Static CSS Contract

These are text-based checks on `style.css` and templates:

| Check | Requirement | Failure Code |
|---|---|---|
| phase1 hide-left override | `body.hide-left .shell.phase1-shell` with grid-template-columns | `MISSING_PHASE1_HIDE_LEFT_OVERRIDE` |
| phase1 main grid | `.shell.phase1-shell .main` with `grid-column: 1 / -1` | `MISSING_PHASE1_MAIN_GRID_COLUMN` |
| detail width contract | `.session-detail-phase1` with width/max-width | `MISSING_SESSION_DETAIL_WIDTH_CONTRACT` |
| hero single column | `.session-detail-phase1 .hero-main` with `grid-template-columns: 1fr` | `HERO_MAIN_STILL_TWO_COLUMN` |
| title wrapping | no `overflow-wrap: anywhere` or `word-break: break-all` | `HERO_TITLE_UNSAFE_ANYWHERE_WRAP` |
| session shell class hook | `session.html` declares `{% block shell_class %}` with phase1-shell + no-inspector | `MISSING_SESSION_SHELL_CLASS_HOOK` |
| base shell application | `base.html` applies shell_class to .shell | `MISSING_BASE_SHELL_CLASS_APPLICATION` |

## Template Contract

These are pytest checks on template structure:

| Check | File | Requirement |
|---|---|---|
| .shell container | base.html | exists with shell_class block |
| .main container | base.html | exists |
| shell_class declaration | session.html | phase1-shell + no-inspector |
| detail root | session.html | .session-detail-phase1 exists |
| hero title | session.html | .hero-title class hook |
| KPI/metrics | session.html | .kpis or .metrics-strip |
| trace rows | session.html | .trace-row class hook |

## Why These Are Deterministic

All metrics come from browser APIs that return exact pixel values:

- `getComputedStyle().gridTemplateColumns` — resolved CSS grid track sizes
- `getBoundingClientRect()` — layout box geometry in viewport coordinates
- `document.documentElement.scrollWidth` — total scrollable width

No screenshot comparison, no subjective "looks wrong" judgment.
If a metric violates a threshold, the gate fails with a specific failure code and `nextInspection` guidance.
