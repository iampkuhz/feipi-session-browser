# Design: Query、Diagnostics、Route 数据需求全量契约

## 1. 概述

本 design 冻结 S4 stage 中 Java 查询和应用层必须实现的全部数据契约。审计覆盖以下 Python 模块：

- `src/session_browser/index/queries.py`
- `src/session_browser/index/metrics.py`
- `src/session_browser/index/diagnostics.py`
- `src/session_browser/index/anomalies.py`
- `src/session_browser/index/percentiles.py`
- `src/session_browser/web/routes.py`
- `src/session_browser/web/view_models.py`
- `src/session_browser/web/presenters/dashboard.py`
- `src/session_browser/web/presenters/sessions.py`

## 2. 契约分类

### 2.1 Query DTO（数据库边界）

Java repository 层必须返回的 typed record。字段名对应 SQLite sessions 表列。

| 契约 ID | 名称 | 字段 | 调用者 |
|---------|------|------|--------|
| Q-SUMMARY | SessionSummary | session_key, session_id, agent, title, project_key, project_name, model, started_at, ended_at, duration_seconds, file_path, fresh_input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, total_tokens, tool_call_count, failed_tool_count, user_message_count, assistant_message_count, subagent_instance_count, model_execution_seconds, tool_execution_seconds | queries.get_session, list_sessions, presenters |
| Q-PROJECT-STATS | ProjectStats | project_key, project_name, total_sessions, claude_sessions, codex_sessions, qoder_sessions, first_seen, last_seen, total_fresh_input_tokens, total_output_tokens, total_cache_read_tokens, total_cache_write_tokens, total_tool_calls, total_failed_tools, total_user_messages, total_assistant_messages | queries.get_project_stats, list_projects |
| Q-TOKEN-BREAKDOWN | TokenBreakdown | total_fresh_input, total_output, total_cache_read, total_cache_write, total_tool_calls, total_failed_tools | metrics.get_token_breakdown |
| Q-DASHBOARD-STATS | DashboardStats | total_sessions, claude_sessions, codex_sessions, qoder_sessions, project_count, total_tokens, total_fresh_input_tokens, total_cache_read_tokens, total_cache_write_tokens, total_output_tokens, total_tool_calls, total_failed_tools, total_user_messages, total_assistant_messages | queries.get_dashboard_stats |
| Q-TREND-ROW | TrendRow | date, claude_count, codex_count, qoder_count, claude_tokens, codex_tokens, qoder_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens, output_tokens, total_tokens, tool_calls, failed_tools, total_count | queries.get_trend_data |
| Q-PROMPT-TREND-ROW | PromptTrendRow | date, claude_prompts, codex_prompts, qoder_prompts, total_prompts, assistant_turns, tool_calls | queries.get_prompt_activity_trend |

### 2.2 Domain Filter（应用层 typed request）

| 契约 ID | 名称 | 字段 | 说明 |
|---------|------|------|------|
| F-SESSION-LIST | SessionListFilter | agent?, project_key?, model?, title_like?, failure_status?, limit, offset, order_by, order_dir | 对应 list_sessions/count_sessions 参数 |
| F-PROJECT-LIST | ProjectListFilter | title_like?, limit, offset, order_by, order_dir | 对应 list_projects/count_projects 参数 |
| F-DASHBOARD | DashboardFilter | agent_scope?, grain?, page?, page_size? | 对应 build_dashboard_view_model 参数 |
| F-SORT-ORDER | SortOrderAllowlist | session: ended_at/started_at/fresh_input_tokens/total_tokens/assistant_message_count/tool_call_count/duration_seconds/process_seconds/failed_tool_count/subagent_instance_count; project: sessions/tokens/tools/failed/first_seen/last_active | 防止 SQL 注入 |

### 2.3 Presentation Model（Web-only view model）

| 契约 ID | 名称 | 消费 route/template | Web-only 字段 |
|---------|------|---------------------|---------------|
| VM-DASHBOARD | DashboardViewModel | dashboard.html | kpis, chart_notes, all_agents_branch, single_agent_branch, cache_health, agent_sessions_page* |
| VM-SESSIONS | SessionsViewModel | sessions.html | sessions_enriched (含 anomaly 字段), filter_*, sort_*, model_list, project_list, sessions_aggregate |
| VM-PROJECTS | ProjectsViewModel | projects.html | projects (ProjectStats list), filter_q, sort_* |
| VM-PROJECT-DETAIL | ProjectDetailViewModel | project.html | project, sessions, trend_grain, project_detail_stats |
| VM-SESSION-DETAIL | SessionDetailViewModel | session.html | session_summary, hero_metrics, issue_links, trace_rows, payload_sources |
| VM-PAYLOAD | PayloadSourceViewModel | session detail attribution | payload_id, kind, title, status, size, text, html, warning, data, token_estimate* |
| VM-TRACE-ROW | TraceRowViewModel | timeline row | round_id, title, status_key, status_label, status_tone, preview_title, preview_subtitle |
| VM-PAGINATION | PaginationViewModel | 所有列表页 | page, current_page, page_size, total_pages, total_count, page_start, page_end, has_prev, has_next |

### 2.4 Diagnostics Registry（冻结枚举和阈值）

| 契约 ID | 名称 | 值 | 消费者 |
|---------|------|----|--------|
| D-PARSE-SEVERITY | ParseSeverity | INFO, WARNING, CRITICAL | diagnostics.to_dict, templates |
| D-PARSE-ISSUE | ParseIssue | BAD_JSON, NON_OBJECT_SKIPPED, FILE_NOT_FOUND, EMPTY_FILE, MISSING_TIMESTAMP, TOKEN_ESTIMATED | diagnostics.to_dict |
| D-SESSION-ANOMALY | SESSION_ANOMALY_DEFINITIONS | long_duration(warn:3600s, crit:7200s), failed_run(warn:15%, crit:25%), cache_write_spike(warn:200000) | anomalies.detect_session_anomalies |
| D-ROUND-SIGNAL | ROUND_SIGNAL_DEFINITIONS | failed-tool, llm-error, long-tool(300s), tool-burst(20), high-write(300K), large-input(200K+50%) | session_detail.anomalies.compute_round_signals |
| D-ANOMALY-TYPE | AnomalyType | long_duration, cache_write_spike, failed_run, payload_visibility_mismatch | anomalies, routes, templates |
| D-FALLBACK-THRESHOLDS | FALLBACK_THRESHOLDS | duration_seconds(w:3600,c:7200), tool_call_count(w:200,c:500), cache_write_tokens(w:200000,c:500000) | percentiles, anomalies |

### 2.5 Derived Metrics（应用层计算）

| 契约 ID | 名称 | 公式 | 空值语义 |
|---------|------|------|----------|
| M-DERIVED | compute_derived_metrics | input_side_total = fresh + cache_read + cache_write; cache_reuse_ratio = cache_read / input_side_total; cache_write_ratio = cache_write / input_side_total; output_ratio = output / input_side_total; tools_per_round = tools / rounds; tokens_per_round = (input_side_total + output) / rounds; tokens_per_minute = (input_side_total + output) / (duration/60); output_per_minute = output / (duration/60) | 全部使用 None 表示除零或未定义；round 精度：ratio 4位, tools_per_round 2位, tokens_per_round 1位, per_minute 1位 |
| M-AGGREGATE | compute_aggregate_metrics | 同 M-DERIVED 但跨所有 session 聚合 | 同上 |
| M-AGENT-EFFICIENCY | compute_agent_efficiency | 按 agent+model 分组：session_count, avg_duration, p95_duration, avg_input_side, avg_tools, tools_per_round, cache_reuse_ratio, failed_per_session | p95 使用 nearest-rank 近似 |

### 2.6 Route 数据需求枚举

| Route | 数据依赖 | 说明 |
|-------|----------|------|
| GET / | DashboardViewModel | agent_scope, grain, page query params |
| GET /sessions | SessionsViewModel | filter, sort, pagination, anomaly enrichment |
| GET /sessions/{agent}/{session_id} | SessionDetailViewModel + source parser | DB lookup + raw JSONL parse + rounds + llm_calls + anomaly + round_signals |
| GET /projects | ProjectsViewModel | filter, sort, pagination |
| GET /projects/{key} | ProjectDetailViewModel | project stats + session list + trend |
| GET /api/sessions/{agent}/{session_id}/payload/{id} | 完整 payload JSON | source parse + rounds + llm_calls + payload lookup (truncate=false) |
| GET /api/sessions/{agent}/{session_id}/attribution/{round}/{call}/{kind} | attribution JSON | source parse + rounds + attribution builder |
| GET /api/sessions/{agent}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind} | subagent attribution JSON | 同上 + subagent LLM call lookup |
| GET /api/sessions/{agent}/{session_id}/round/{index} | round HTML fragment | source parse + rounds + view model (round filter) |
| GET /api/sessions/{agent}/{session_id}/bucket-detail/{round}/{key} | bucket detail JSON | current_user_message / local_instruction_context / full_messages_array_item |

### 2.7 Session Detail 对 artifact/raw source/attribution 的读取

| 数据源 | 读取方式 | 用途 |
|--------|----------|------|
| DB sessions 表 | get_session(session_key) | 列表页和详情页基准数据 |
| Raw JSONL | parse_{claude/codex/qoder}_session_detail | 提取 messages, tool_calls, subagent_runs |
| Memory cache | _get/_set_cached_session_data | 避免重复解析 |
| Normalized artifact | session.file_path | Qoder 文件定位 |
| Attribution context | build_attribution_session_context | 构建 bucket 分配上下文 |
| Payload lookup | _build_payload_lookup | 构建 payload_id -> content 映射 |

## 3. QA Task 归属

| QA Task | 覆盖契约 |
|---------|----------|
| QA-020 | F-SESSION-LIST, F-PROJECT-LIST, F-SORT-ORDER, F-DASHBOARD, Q-SUMMARY |
| QA-030 | get_session, list_sessions, count_sessions, get_sessions_list_aggregate |
| QA-040 | get_dashboard_stats, get_trend_data, get_prompt_activity_trend, Q-TOKEN-BREAKDOWN, Q-DASHBOARD-STATS, Q-TREND-ROW, Q-PROMPT-TREND-ROW, get_token_breakdown, get_model_distribution, get_agent_distribution, get_tool_distribution, get_top_projects_by_tokens, get_top_projects_by_tools, get_slowest_sessions, get_failed_tool_sessions, get_high_cache_read_sessions, compute_aggregate_metrics, compute_agent_efficiency |
| QA-050 | session detail route, payload route, attribution routes, round API, bucket-detail API, session parse/cache/merge |
| QA-060 | D-PARSE-SEVERITY, D-PARSE-ISSUE, D-SESSION-ANOMALY, D-ROUND-SIGNAL, D-ANOMALY-TYPE, D-FALLBACK-THRESHOLDS, detect_session_anomalies, detect_all_anomalies, get_needs_attention, compute_round_signals, percentiles |
| QA-070 | VM-DASHBOARD, VM-SESSIONS, VM-PROJECTS, VM-PROJECT-DETAIL, VM-SESSION-DETAIL, M-DERIVED, M-AGGREGATE, M-AGENT-EFFICIENCY, presenters |

## 4. Validation Placement

| 校验条件 | 唯一主要位置 | 下游行为 |
|----------|-------------|----------|
| sort_by/order_by 合法性 | Web adapter / presenter (allowlist map) | application 使用 typed enum, repository 不再检查 |
| agent_scope URL 值 -> DB 值映射 | Web adapter (_AGENT_SCOPE_MAP / _DB_AGENT) | application 使用 DB agent 字符串 |
| page/page_size 范围 | Web adapter (parse_sessions_query_params) | application 使用已验证的 int |
| session_key 格式 | repository (parameterized SQL) | application 信任 typed session_key |
| anomaly severity/type 值 | domain enum (AnomalyType, ParseSeverity) | template 直接渲染，不再校验 |
| title_like SQL 注入 | Web adapter 参数化; repository 只做 LIKE pattern | 不重复校验 |
| 除零保护 | derived metrics 计算点 (safe_div) | consumer 信任已计算的 None/值 |
