# Tasks: Fix Session Detail Runtime

- [x] 1. Inspect current app entrypoints and session detail route — confirm `ConversationRound.title` is the sole failure point
- [x] 2. Fix backend issue: replace `r.title` with `r.preview_text` in `routes.py:1491`
- [x] 3. Add route smoke test for session detail — start server, request session URL, assert HTTP 200 and key DOM elements
- [x] 4. Verify server renders session detail page with HTTP 200
- [x] 5. Run full test suite — ensure no regressions (679 passed, 0 failed)
- [x] 6. Run OpenSpec/harness validation scripts (2 pre-existing failures unrelated to this change)
- [x] 7. Document runtime command and validation evidence
