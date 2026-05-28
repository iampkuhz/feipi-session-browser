# Tasks: Group Session Detail KPIs

Walk these tasks sequentially. Mark each checkbox with validation evidence when done.

## Phase 1: KPI grouping

- [x] 1.1 Add token metric fields to the session detail hero view model.
  - Validation: `python3 -m pytest tests/rendering/test_template_render.py tests/session_detail/test_session_detail_template_contract.py`

- [x] 1.2 Split `.sd-kpis` into token analysis and call-count analysis groups.
  - Validation: `python3 -m pytest tests/rendering/test_template_render.py tests/session_detail/test_session_detail_template_contract.py`

- [x] 1.3 Update the long-term session detail UI spec.
  - Validation: `python3 scripts/harness/validate_openspec_layout.py`
