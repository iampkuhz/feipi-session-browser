# Session Detail v18 Context

Current references:

```text
docs/ui/reference/session-detail-v18-current/
  01-current-modal-metadata-and-llm-card.png
  02-current-expanded-round-layout.png
  current-session-detail-page.mhtml
```

Observed:
- modal is centered, but metadata rail is still naked text and visually broken.
- expanded user-message round loses green/teal visual tone.
- Response button inside LLM call card stretches too wide.

Target: ~~docs/ui/hifi/session_detail_v18/index.html~~ (deleted 2026-05; use current `src/session_browser/web/templates/session.html` + `components/session_detail_timeline.html` as baseline)

Relevant repo facts from public GitHub:
- `static/css` has multiple CSS files, including canonical `session-detail-timeline.css` and older versioned detail CSS.
- `templates/components` has versioned session-detail templates. Do not reintroduce legacy imports.
