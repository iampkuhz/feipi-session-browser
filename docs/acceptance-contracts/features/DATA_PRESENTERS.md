# Presenter 层 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | Presenter 层（数据→视图模型转换） |
| 关联源码 | `src/session_browser/web/presenters/`（sessions, dashboard, projects, session_detail） |
| 关联测试 | `tests/web/test_sessions_presenter.py`、`test_dashboard_presenter.py`、`test_projects_presenter.py`、`web/test_make_round.py`、`web/test_round_signals.py` 等 |
| 主要风险 | presenter 数据模型与模板期望不匹配；分页计算错误；token 归一化丢失精度 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| DATA-PRESENTER-001 | P0 | data | Sessions Presenter 返回列表视图模型 | 调用 `fetch_sessions_view_model` 带有效 query params | 返回 dict 含 sessions 列表、pagination、aggregate_stats，每行含 agent/model/title 字段 | pytest | — | 待补充 |
| DATA-PRESENTER-002 | P0 | data | Dashboard Presenter 构建完整视图模型 | 调用 `build_dashboard_view_model` | 返回含 stats/trend_data/model_distribution/agent_distribution 的 dict | pytest | — | 待补充 |
| DATA-PRESENTER-003 | P0 | data | Projects Presenter 返回项目列表视图模型 | 调用 `build_projects_view_model` | 返回含 projects 列表、aggregate、pagination | pytest | — | 待补充 |
| DATA-PRESENTER-004 | P0 | data | Agent Presenter 返回 Agent 列表视图模型 | 调用 `build_agents_view_model` | 返回含 agents 列表、aggregate stats | pytest | — | 待补充 |
| DATA-PRESENTER-005 | P0 | data | Session Detail 轮次构建（build_rounds） | 给定 ChatMessage + ToolCall 列表调用 `build_rounds` | 返回 ConversationRound 列表，每个 round 含 user_msg/assistant_msg/tools 关联正确 | pytest | — | 待补充 |
| DATA-PRESENTER-006 | P0 | data | Timeline 轮次调查信号计算（`compute_round_signals`） | 给定含失败 tool、LLM error、长耗时 tool、高 tool 数、cache write 或大输入 token 的 round | 返回只包含 `key`/`label`/`severity`/`reason` 的信号字典；当前信号包括 `failed-tool`、`llm-error`、`long-tool`、`tool-burst`、`high-write`、`large-input`；不得产生 `warm-up`、`cache-hit`、`low-output`、`llm-burst` | pytest | — | 待补充 |
| DATA-PRESENTER-007 | P0 | data | Sessions 分页计算（page size / offset / has_next） | 调用 `compute_pagination(total=150, page=3, page_size=20)` | `page=3`, `total_pages=8`, `has_next=True`, `has_prev=True` | pytest | — | 待补充 |
| DATA-PRESENTER-008 | P1 | data | Token 条归一化（四段：input/output/cached-in/cached-out） | 调用 `normalize_tokens` 带完整 usage dict | 返回 `TokenBreakdown` 含 input_tokens/output_tokens/cached_input/cached_output | pytest | — | 待补充 |
| DATA-PRESENTER-009 | P1 | data | LLM Calls 数据构建（session detail） | 给定 assistant messages 调用 `build_llm_calls` | 返回 LLMCall 列表，含 model/usage/token_breakdown/tool_calls | pytest | — | `tests/session_detail/test_session_detail_llm_call_contract.py` |
| DATA-PRESENTER-010 | P1 | data | LLM Payload API 语义（payload 文本不截断） | 调用 payload API 端点 | 返回的 payload text 包含完整内容，未被预览长度截断 | pytest | — | 待补充 |
| DATA-PRESENTER-011 | P1 | data | 轮次一致性（round 数 = user+assistant 消息对数） | 给定 N 个 user msg 和 M 个 assistant msg | `build_rounds` 返回的 round 数与预期一致，无 orphan 消息 | pytest | — | 待补充 |
| DATA-PRESENTER-013 | P2 | data | Token 变量同源性（presenter 与模板使用同一 token 变量源） | 比较 presenter 输出的 token breakdown 与模板渲染值 | 两者数值一致，不存在 presenter 有但模板不展示的字段 | pytest | — | `tests/ui/test_token_variable_homology.py` |
| DATA-PRESENTER-014 | P2 | data | 页面大小一致性（所有列表页默认 page_size 一致） | 检查各 presenter 默认 page_size 参数 | 所有列表页 page_size 统一为 20（或配置值） | pytest | — | 待补充 |
