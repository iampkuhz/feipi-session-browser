# Session Detail v17 Complete Context

Target repository:

```text
/Users/zhehan/Documents/tools/llm/feipi-session-browser
```

Reference public repository observations:

- `src/session_browser/web/static/css/` currently includes `session-browser-v15.css`, `session-detail-response-blocks-v12.css`, `session-detail-timeline-v11.css`, `session-detail-timeline.css`, `sessions-list.css`, and `ui-primitives.css`.
- `src/session_browser/web/templates/components/` currently includes versioned session-detail component files such as `session_detail_timeline.html`, `session_detail_timeline_v11.html`, and `session_detail_timeline_v12.html`.
- Current `session_detail_timeline.html` has very compact/minified Jinja and is likely hard to modify safely.
- Current `session_detail_timeline.js` is very short in GitHub's rendered view, so local repository inspection is mandatory.

Reference broken screenshots:

```text
docs/ui/reference/session-detail-v17-current-bad/01-current-session-detail-trace.png
docs/ui/reference/session-detail-v17-current-bad/02-current-open-modal-fullpage.png
docs/ui/reference/session-detail-v17-current-bad/03-current-context-modal-fullpage.png
```

Reference target:

```text
docs/ui/hifi/session_detail_v17/index.html
```
