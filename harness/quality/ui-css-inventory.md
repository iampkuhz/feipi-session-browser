# UI CSS Inventory

Long-lived harness asset.

## Current CSS files expected

```text
src/session_browser/web/static/style.css
src/session_browser/web/static/css/ui-primitives.css
src/session_browser/web/static/css/session-detail-timeline.css
src/session_browser/web/static/css/sessions-list.css
src/session_browser/web/static/css/session-browser-v15.css
```

## Ownership

| File | Owner | Scope |
|---|---|---|
| `style.css` | design-system | base tokens, legacy base app shell |
| `ui-primitives.css` | design-system-components | shared primitive helpers |
| `session-detail-timeline.css` | session-detail-page | trace / round / tool / subagent layout |
| `sessions-list.css` | sessions-list-page | sessions list |
| `session-browser-v15.css` | page-system-v15 | final high fidelity baseline for dashboard/sessions/session/projects/agents |

Any new CSS file must update this inventory in the same change.
