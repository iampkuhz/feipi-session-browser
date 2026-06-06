# 验收检查矩阵

> 本表列出所有验收契约用例的 ID、优先级、分层和关联测试文件。按模块分组。

## 数据源模块（DATA-SOURCE-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| DATA-SOURCE-001 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_claude_source.py` |
| DATA-SOURCE-002 | P0 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/claude.py` |
| DATA-SOURCE-003 | P0 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/claude.py` |
| DATA-SOURCE-004 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_claude_source.py` |
| DATA-SOURCE-005 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_codex_source.py` |
| DATA-SOURCE-006 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_codex_source.py` |
| DATA-SOURCE-007 | P0 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/codex.py` |
| DATA-SOURCE-008 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_qoder_model_contract.py` |
| DATA-SOURCE-009 | P0 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/qoder.py` |
| DATA-SOURCE-010 | P0 | data | `features/DATA_SOURCES.md` | `tests/backend/test_qoder_token_estimation.py` |
| DATA-SOURCE-011 | P0 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/qoder.py` |
| DATA-SOURCE-012 | P1 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/qoder.py` |
| DATA-SOURCE-013 | P1 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/qoder.py` |
| DATA-SOURCE-014 | P1 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/claude.py` |
| DATA-SOURCE-015 | P1 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/claude.py` |
| DATA-SOURCE-016 | P2 | data | `features/DATA_SOURCES.md` | `src/session_browser/sources/qoder.py` |

## 数据索引模块（DATA-INDEX-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| DATA-INDEX-001 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_full_scan_fixture.py` |
| DATA-INDEX-002 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_incremental_scan.py` |
| DATA-INDEX-003 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_full_vs_incremental_consistency.py` |
| DATA-INDEX-004 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_new_file_scenario.py` |
| DATA-INDEX-005 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_modified_file_scenario.py` |
| DATA-INDEX-006 | P0 | data | `features/DATA_INDEX.md` | `tests/index/test_bad_json_isolation.py` |
| DATA-INDEX-007 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_delete_file_contract.py` |
| DATA-INDEX-008 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_qoder_canonical_dedup.py` |
| DATA-INDEX-009 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_qoder_incremental_update.py` |
| DATA-INDEX-010 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_qoder_locator_expansion.py` |
| DATA-INDEX-011 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_qoder_project_path_contract.py` |
| DATA-INDEX-012 | P1 | data | `features/DATA_INDEX.md` | `tests/index/test_sessions_filters.py` |
| DATA-INDEX-013 | P2 | data | `features/DATA_INDEX.md` | `src/session_browser/index/indexer.py` |

## Presenter 层（DATA-PRESENTER-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| DATA-PRESENTER-001 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_sessions_presenter.py` |
| DATA-PRESENTER-002 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_dashboard_presenter.py` |
| DATA-PRESENTER-003 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_projects_presenter.py` |
| DATA-PRESENTER-004 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_projects_presenter.py` |
| DATA-PRESENTER-005 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/backend/test_make_round.py` |
| DATA-PRESENTER-006 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/backend/test_round_signals.py` |
| DATA-PRESENTER-007 | P0 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_sessions_pagination_has_next.py` |
| DATA-PRESENTER-008 | P1 | data | `features/DATA_PRESENTERS.md` | `tests/backend/test_token_bar_normalization.py` |
| DATA-PRESENTER-009 | P1 | data | `features/DATA_PRESENTERS.md` | `tests/session_detail/test_session_detail_llm_call_contract.py` |
| DATA-PRESENTER-010 | P1 | data | `features/DATA_PRESENTERS.md` | `tests/session_detail/test_session_detail_llm_payload_semantics.py` |
| DATA-PRESENTER-011 | P1 | data | `features/DATA_PRESENTERS.md` | `tests/session_detail/test_session_detail_round_consistency.py` |
| DATA-PRESENTER-012 | P1 | data | `features/DATA_PRESENTERS.md` | `src/session_browser/web/presenters/agents.py` |
| DATA-PRESENTER-013 | P2 | data | `features/DATA_PRESENTERS.md` | `tests/ui/test_token_variable_homology.py` |
| DATA-PRESENTER-014 | P2 | data | `features/DATA_PRESENTERS.md` | `tests/web/test_page_size_consistency.py` |

## 路由与 API（ROUTE-API-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| ROUTE-API-001 | P0 | data | `features/ROUTES_AND_API.md` | `tests/session_detail/test_session_detail_route.py` |
| ROUTE-API-002 | P0 | data | `features/ROUTES_AND_API.md` | `tests/session_detail/test_session_detail_api.py` |
| ROUTE-API-003 | P0 | data | `features/ROUTES_AND_API.md` | `tests/rendering/test_safe_render.py` |
| ROUTE-API-004 | P0 | data | `features/ROUTES_AND_API.md` | `tests/web/test_template_env.py` |
| ROUTE-API-005 | P1 | data | `features/ROUTES_AND_API.md` | `src/session_browser/web/routes.py` |
| ROUTE-API-006 | P1 | data | `features/ROUTES_AND_API.md` | `src/session_browser/web/routes.py` |
| ROUTE-API-007 | P1 | data | `features/ROUTES_AND_API.md` | `src/session_browser/web/routes.py` |
| ROUTE-API-008 | P1 | data | `features/ROUTES_AND_API.md` | `src/session_browser/web/routes.py` |
| ROUTE-API-009 | P1 | data | `features/ROUTES_AND_API.md` | `src/session_browser/web/routes.py` |
| ROUTE-API-010 | P1 | visual | `features/ROUTES_AND_API.md` | `tests/playwright/ui-contract.spec.ts` |
| ROUTE-API-011 | P1 | data | `features/ROUTES_AND_API.md` | `tests/web/test_presenter_route_integration.py` |
| ROUTE-API-012 | P2 | data | `features/ROUTES_AND_API.md` | `tests/web/test_sessions_ajax_partial.py` |

## Dashboard（UI-DASHBOARD-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-DASHBOARD-001 | P0 | visual | `features/UI_DASHBOARD.md` | `tests/pages/test_dashboard.py` |
| UI-DASHBOARD-002 | P0 | visual | `features/UI_DASHBOARD.md` | `tests/playwright/macbook-smoke.spec.js` |
| UI-DASHBOARD-003 | P0 | visual | `features/UI_DASHBOARD.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-DASHBOARD-004 | P0 | data | `features/UI_DASHBOARD.md` | `tests/web/test_dashboard_presenter.py` |
| UI-DASHBOARD-005 | P1 | visual | `features/UI_DASHBOARD.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-DASHBOARD-006 | P1 | visual | `features/UI_DASHBOARD.md` | `tests/ui/test_dashboard_tooltip_contract.py` |
| UI-DASHBOARD-007 | P1 | visual | `features/UI_DASHBOARD.md` | `tests/playwright/macbook-smoke.spec.js` |
| UI-DASHBOARD-008 | P1 | visual | `features/UI_DASHBOARD.md` | `tests/pages/test_dashboard_page.py` |

## Sessions List（UI-SESSIONS-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-SESSIONS-001 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_sessions_list.py` |
| UI-SESSIONS-002 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-003 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-004 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-005 | P0 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-006 | P0 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-007 | P0 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-008 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-009 | P0 | visual | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_sessions_list_contract.py` |
| UI-SESSIONS-010 | P1 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_apply_dirty_state.py` |
| UI-SESSIONS-011 | P1 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/web/test_sessions_ajax_partial.py` |
| UI-SESSIONS-012 | P1 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_sessions_pagination.py` |
| UI-SESSIONS-013 | P1 | visual | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_list_title_truncation.py` |
| UI-SESSIONS-014 | P1 | interaction | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_sessions_list_query_state.py` |
| UI-SESSIONS-015 | P1 | visual | `features/UI_SESSIONS_LIST.md` | `tests/playwright/sessions-list.spec.js` |
| UI-SESSIONS-016 | P1 | visual | `features/UI_SESSIONS_LIST.md` | `tests/rendering/test_sessions_token_cell_contract.py` |
| UI-SESSIONS-017 | P2 | visual | `features/UI_SESSIONS_LIST.md` | `tests/sessions_list/test_sessions_list.py` |

## Session Detail（UI-SD-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-SD-001 | P0 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-002 | P0 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-003 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-004 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-005 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-006 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-007 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-008 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-009 | P0 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-010 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-011 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-012 | P0 | interaction | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-013 | P0 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail-layout.spec.js` |
| UI-SD-014 | P0 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/shell-states.spec.js` |
| UI-SD-015 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-SD-016 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_template_contract.py` |
| UI-SD-017 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_trace_dom_contract.py` |
| UI-SD-018 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_trace_layout_contract.py` |
| UI-SD-019 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_trace_preview_contract.py` |
| UI-SD-020 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/rendering/test_payload_modal_renderer_contract.py` |
| UI-SD-021 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/rendering/test_tool_result_render.py` |
| UI-SD-022 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/rendering/test_trace_header_contract.py` |
| UI-SD-023 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/rendering/test_session_detail_tabs_contract.py` |
| UI-SD-024 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_preview_tag.py` |
| UI-SD-025 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/ui/test_tool_status.py` |
| UI-SD-026 | P1 | data | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_missing_raw_payload.py` |
| UI-SD-027 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-028 | P1 | visual | `features/UI_SESSION_DETAIL.md` | `tests/playwright/session-detail.spec.js` |
| UI-SD-029 | P2 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_noise_and_a11y.py` |
| UI-SD-030 | P2 | visual | `features/UI_SESSION_DETAIL.md` | `tests/session_detail/test_session_detail_hifi_contract.py` |

## Projects（UI-PROJECTS-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-PROJECTS-001 | P0 | visual | `features/UI_PROJECTS.md` | `tests/pages/test_projects_page.py` |
| UI-PROJECTS-002 | P0 | visual | `features/UI_PROJECTS.md` | `tests/pages/test_project_detail_page.py` |
| UI-PROJECTS-003 | P0 | visual | `features/UI_PROJECTS.md` | `tests/rendering/test_project_detail_table_contract.py` |
| UI-PROJECTS-004 | P0 | data | `features/UI_PROJECTS.md` | `tests/web/test_projects_presenter.py` |
| UI-PROJECTS-005 | P0 | visual | `features/UI_PROJECTS.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-PROJECTS-006 | P0 | visual | `features/UI_PROJECTS.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-PROJECTS-007 | P0 | visual | `features/UI_PROJECTS.md` | `tests/rendering/test_project_template_contract.py` |
| UI-PROJECTS-008 | P0 | visual | `features/UI_PROJECTS.md` | `tests/rendering/test_projects_template_contract.py` |
| UI-PROJECTS-009 | P1 | visual | `features/UI_PROJECTS.md` | `tests/playwright/macbook-smoke.spec.js` |
| UI-PROJECTS-010 | P2 | interaction | `features/UI_PROJECTS.md` | 待补充 |

## Agents（UI-AGENTS-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-AGENTS-001 | P0 | visual | `features/UI_AGENTS.md` | `tests/pages/test_agents_list_page.py` |
| UI-AGENTS-002 | P0 | visual | `features/UI_AGENTS.md` | `tests/pages/test_agent_detail.py` |
| UI-AGENTS-003 | P0 | visual | `features/UI_AGENTS.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-AGENTS-004 | P0 | visual | `features/UI_AGENTS.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-AGENTS-005 | P0 | visual | `features/UI_AGENTS.md` | `tests/playwright/macbook-smoke.spec.js` |
| UI-AGENTS-006 | P0 | visual | `features/UI_AGENTS.md` | `tests/pages/test_agents_page.py` |
| UI-AGENTS-007 | P2 | interaction | `features/UI_AGENTS.md` | 待补充 |
| UI-AGENTS-008 | P2 | interaction | `features/UI_AGENTS.md` | 待补充 |

## Glossary（UI-GLOSSARY-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-GLOSSARY-001 | P0 | visual | `features/UI_GLOSSARY.md` | `tests/pages/test_glossary_page.py` |
| UI-GLOSSARY-002 | P0 | visual | `features/UI_GLOSSARY.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-GLOSSARY-003 | P2 | interaction | `features/UI_GLOSSARY.md` | 待补充 |

## 全局视觉（UI-VISUAL-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-VISUAL-001 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-002 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-003 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/session-detail-layout.spec.js` |
| UI-VISUAL-004 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-005 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-006 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/shell-states.spec.js` |
| UI-VISUAL-007 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/playwright/ui-contract.spec.ts` |
| UI-VISUAL-008 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/pages/test_2560x1440_smoke.py` |
| UI-VISUAL-009 | P0 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/pages/test_macbook_smoke.py`、`tests/playwright/macbook-smoke.spec.js` |
| UI-VISUAL-010 | P1 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/pages/test_scroll_shadow_behavior.py` |
| UI-VISUAL-011 | P1 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/ui/test_ui_density_and_font_size.py` |
| UI-VISUAL-012 | P1 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/ui/test_ui_primitives.py` |
| UI-VISUAL-013 | P1 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/ui/test_hifi_dom_structure.py` |
| UI-VISUAL-014 | P1 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/ui/test_card_sub_spacing.py` |
| UI-VISUAL-015 | P2 | visual | `features/UI_GLOBAL_VISUAL.md` | `tests/pages/test_state_pages.py` |

## 交互（UI-INTERACTION-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| UI-INTERACTION-001 | P0 | interaction | `features/UI_INTERACTIONS.md` | `tests/pages/test_sidebar_toggle.py` |
| UI-INTERACTION-002 | P0 | interaction | `features/UI_INTERACTIONS.md` | `tests/sessions_list/test_sessions_list_interactions.py` |
| UI-INTERACTION-003 | P0 | interaction | `features/UI_INTERACTIONS.md` | `tests/web/test_sessions_ajax_partial.py` |
| UI-INTERACTION-004 | P0 | interaction | `features/UI_INTERACTIONS.md` | `tests/web/test_sessions_pagination_has_next.py` |
| UI-INTERACTION-005 | P1 | interaction | `features/UI_INTERACTIONS.md` | `tests/rendering/test_copy_action_contract.py` |
| UI-INTERACTION-006 | P1 | interaction | `features/UI_INTERACTIONS.md` | `tests/pages/test_profile_modal_open.py` |
| UI-INTERACTION-007 | P1 | interaction | `features/UI_INTERACTIONS.md` | `tests/pages/test_timeline_expandability.py` |
| UI-INTERACTION-008 | P1 | visual | `features/UI_INTERACTIONS.md` | `tests/pages/test_timeline_preview.py` |
| UI-INTERACTION-009 | P1 | interaction | `features/UI_INTERACTIONS.md` | `tests/sessions_list/test_apply_dirty_state.py` |
| UI-INTERACTION-010 | P1 | interaction | `features/UI_INTERACTIONS.md` | `tests/sessions_list/test_sessions_list_query_state.py` |
| UI-INTERACTION-011 | P2 | interaction | `features/UI_INTERACTIONS.md` | 待补充 |
| UI-INTERACTION-012 | P2 | interaction | `features/UI_INTERACTIONS.md` | 待补充 |

## Hook/Harness（HOOK-HARNESS-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---:|---|---|---|
| HOOK-HARNESS-001 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_claude_hooks_bash_policy.py` |
| HOOK-HARNESS-002 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_claude_hooks_classify.py` |
| HOOK-HARNESS-003 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_claude_hooks_evidence.py` |
| HOOK-HARNESS-004 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_claude_hooks_file_policy.py` |
| HOOK-HARNESS-005 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_claude_hooks_hook_io.py` |
| HOOK-HARNESS-006 | P0 | data | `features/HOOK_HARNESS.md` | `tests/hooks/test_stop_quality_gate.py` |
| HOOK-HARNESS-007 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_generate_quality_report.py` |
| HOOK-HARNESS-008 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_new_quality_gates.py` |
| HOOK-HARNESS-009 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_quality_artifact.py` |
| HOOK-HARNESS-010 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_quality_gate_runner.py` |
| HOOK-HARNESS-011 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_repo_slimming_contract.py` |
| HOOK-HARNESS-012 | P0 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_run_required_quality_gates.py` |
| HOOK-HARNESS-013 | P1 | data | `features/HOOK_HARNESS.md` | `tests/quality/test_static_contract.py` |
| HOOK-HARNESS-014 | P1 | data | `features/HOOK_HARNESS.md` | `scripts/harness/validate_harness_structure.py` |
| HOOK-HARNESS-015 | P1 | data | `features/HOOK_HARNESS.md` | `scripts/harness/validate_openspec_layout.py` |

## 验收体系（ACCEPTANCE-*）

| 用例 ID | 优先级 | 分层 | 归属文档 | 关联测试文件 |
|---|---|---|---|---|
| ACCEPTANCE-001 | P2 | data | `features/ROUTES_AND_API.md` | `tests/misc/test_cli.py` |

## 统计

| 指标 | 数量 |
|---|---|
| 用例总数 | 173 |
| P0 用例 | 93 |
| P1 用例 | 67 |
| P2 用例 | 13 |
| data 分层 | 85 |
| visual 分层 | 58 |
| interaction 分层 | 27 |
| pytest 关联 | 138 |
| Playwright 关联 | 31 |
| 待补充 | 4 |
