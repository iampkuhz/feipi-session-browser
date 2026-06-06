# Presenter 层 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | Presenter 层（数据→视图模型转换） |
| 关联源码 | `src/session_browser/web/presenters/`（sessions, dashboard, agents, projects, session_detail） |
| 关联测试 | `tests/web/test_sessions_presenter.py`、`test_dashboard_presenter.py`、`test_projects_presenter.py`、`web/test_make_round.py`、`web/test_round_signals.py` 等 |
| 主要风险 | presenter 数据模型与模板期望不匹配；分页计算错误；token 归一化丢失精度 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| DATA-PRESENTER-001 | P0 | data | Sessions Presenter 返回列表视图模型 | 调用 `fetch_sessions_view_model` 带有效 query params | 返回 dict 含 sessions 列表、pagination、aggregate_stats，每行含 agent/model/title 字段 | pytest | — | `tests/web/test_sessions_presenter.py` |
| DATA-PRESENTER-002 | P0 | data | Dashboard Presenter 构建完整视图模型 | 调用 `build_dashboard_view_model` | 返回含 stats/trend_data/model_distribution/agent_distribution 的 dict | pytest | — | `tests/web/test_dashboard_presenter.py` |
| DATA-PRESENTER-003 | P0 | data | Projects Presenter 返回项目列表视图模型 | 调用 `build_projects_view_model` | 返回含 projects 列表、aggregate、pagination | pytest | — | `tests/web/test_projects_presenter.py` |
| DATA-PRESENTER-004 | P0 | data | Agent Presenter 返回 Agent 列表视图模型 | 调用 `build_agents_view_model` | 返回含 agents 列表、aggregate stats | pytest | — | `tests/web/test_projects_presenter.py` |
| DATA-PRESENTER-005 | P0 | data | Session Detail 轮次构建（build_rounds） | 给定 ChatMessage + ToolCall 列表调用 `build_rounds` | 返回 ConversationRound 列表，每个 round 含 user_msg/assistant_msg/tools 关联正确 | pytest | — | `tests/backend/test_make_round.py` |
| DATA-PRESENTER-006 | P0 | data | 轮次信号计算（is_failed / has_tools / has_llm） | 给定含失败 tool 和 assistant msg 的 round | `round.is_failed == True`，`round.has_tools == True` | pytest | — | `tests/backend/test_round_signals.py` |
| DATA-PRESENTER-007 | P0 | data | Sessions 分页计算（page size / offset / has_next） | 调用 `compute_pagination(total=150, page=3, page_size=20)` | `page=3`, `total_pages=8`, `has_next=True`, `has_prev=True` | pytest | — | `tests/web/test_sessions_pagination_has_next.py` |
| DATA-PRESENTER-008 | P1 | data | Token 条归一化（四段：input/output/cached-in/cached-out） | 调用 `normalize_tokens` 带完整 usage dict | 返回 `TokenBreakdown` 含 input_tokens/output_tokens/cached_input/cached_output | pytest | — | `tests/backend/test_token_bar_normalization.py` |
| DATA-PRESENTER-009 | P1 | data | LLM Calls 数据构建（session detail） | 给定 assistant messages 调用 `build_llm_calls` | 返回 LLMCall 列表，含 model/usage/token_breakdown/tool_calls | pytest | — | `tests/session_detail/test_session_detail_llm_call_contract.py` |
| DATA-PRESENTER-010 | P1 | data | LLM Payload 语义（raw payload 字段不截断） | 调用 payload API 端点 | 返回的 raw_payload 包含完整原始内容，未截断 | pytest | — | `tests/session_detail/test_session_detail_llm_payload_semantics.py` |
| DATA-PRESENTER-011 | P1 | data | 轮次一致性（round 数 = user+assistant 消息对数） | 给定 N 个 user msg 和 M 个 assistant msg | `build_rounds` 返回的 round 数与预期一致，无 orphan 消息 | pytest | — | `tests/session_detail/test_session_detail_round_consistency.py` |
| DATA-PRESENTER-012 | P1 | data | Agent 详情视图模型 | 调用 `build_agent_view_model(agent="claude_code")` | 返回含 agent stats、session list、model distribution | pytest | — | `src/session_browser/web/presenters/agents.py` |
| DATA-PRESENTER-013 | P2 | data | Token 变量同源性（presenter 与模板使用同一 token 变量源） | 比较 presenter 输出的 token breakdown 与模板渲染值 | 两者数值一致，不存在 presenter 有但模板不展示的字段 | pytest | — | `tests/ui/test_token_variable_homology.py` |
| DATA-PRESENTER-014 | P2 | data | 页面大小一致性（所有列表页默认 page_size 一致） | 检查各 presenter 默认 page_size 参数 | 所有列表页 page_size 统一为 20（或配置值） | pytest | — | `tests/web/test_page_size_consistency.py` |
