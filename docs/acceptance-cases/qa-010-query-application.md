# QA-010 Query/Application 契约冻结

## 审计范围

逐 function 审计以下 Python 模块，冻结 Java 查询和应用边界：

- `src/session_browser/index/queries.py` (17 functions)
- `src/session_browser/index/metrics.py` (14 functions)
- `src/session_browser/index/diagnostics.py` (5 classes, 3 registries, 4 functions)
- `src/session_browser/index/anomalies.py` (3 classes, 5 functions, 2 constants groups)
- `src/session_browser/index/percentiles.py` (4 functions, 2 constants)
- `src/session_browser/web/routes.py` (11 routes, 6 API endpoints)
- `src/session_browser/web/view_models.py` (8 TypedDict contracts)
- `src/session_browser/web/presenters/dashboard.py` (30+ helper functions)
- `src/session_browser/web/presenters/sessions.py` (5 functions)

## 契约清单

### Query DTO (数据库边界)

1. Q-SUMMARY (SessionSummary): session_key, session_id, agent, title, project_key, project_name, model, started_at, ended_at, duration_seconds, file_path, fresh_input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, total_tokens, tool_call_count, failed_tool_count, user_message_count, assistant_message_count, subagent_instance_count, model_execution_seconds, tool_execution_seconds
2. Q-PROJECT-STATS (ProjectStats): project_key, project_name, total_sessions, claude/codex/qoder_sessions, first_seen, last_seen, token breakdowns, tool/message counts
3. Q-TOKEN-BREAKDOWN (TokenBreakdown): 6 aggregate token/tool counters
4. Q-DASHBOARD-STATS (DashboardStats): 14 aggregate counters including per-agent session counts
5. Q-TREND-ROW (TrendRow): 14 daily aggregate fields
6. Q-PROMPT-TREND-ROW (PromptTrendRow): 6 daily prompt/activity fields

### Domain Filter (应用层 typed request)

7. F-SESSION-LIST (SessionListFilter): agent?, project_key?, model?, title_like?, failure_status?, limit, offset, order_by, order_dir
8. F-PROJECT-LIST (ProjectListFilter): title_like?, limit, offset, order_by, order_dir
9. F-DASHBOARD (DashboardFilter): agent_scope?, grain?, page?, page_size?
10. F-SORT-ORDER (SortOrderAllowlist): session 10 keys, project 6 keys

### Presentation Model (Web-only view model)

11. VM-DASHBOARD (DashboardViewModel): 17 fields including kpis, trend, branches
12. VM-SESSIONS (SessionsViewModel): 15 fields including enriched sessions, filters, aggregates
13. VM-PROJECTS (ProjectsViewModel): 6 fields
14. VM-PROJECT-DETAIL (ProjectDetailViewModel): 10 fields
15. VM-SESSION-DETAIL (SessionDetailViewModel): 6 fields
16. VM-PAYLOAD (PayloadSourceViewModel): 12 fields
17. VM-TRACE-ROW (TraceRowViewModel): 8 fields
18. VM-PAGINATION (PaginationViewModel): 9 fields

### Diagnostics Registry (冻结枚举和阈值)

19. D-PARSE-SEVERITY: INFO, WARNING, CRITICAL
20. D-PARSE-ISSUE: BAD_JSON, NON_OBJECT_SKIPPED, FILE_NOT_FOUND, EMPTY_FILE, MISSING_TIMESTAMP, TOKEN_ESTIMATED
21. D-SESSION-ANOMALY: long_duration(3600/7200s), failed_run(15%/25%), cache_write_spike(200K)
22. D-ROUND-SIGNAL: failed-tool, llm-error, long-tool(300s), tool-burst(20), high-write(300K), large-input(200K+50%)
23. D-ANOMALY-TYPE: long_duration, cache_write_spike, failed_run, payload_visibility_mismatch
24. D-FALLBACK-THRESHOLDS: duration_seconds(3600/7200), tool_call_count(200/500), cache_write_tokens(200K/500K)

### Derived Metrics (应用层计算)

25. M-DERIVED (compute_derived_metrics): 8 derived fields with None for undefined ratios
26. M-AGGREGATE (compute_aggregate_metrics): 6 aggregate derived fields
27. M-AGENT-EFFICIENCY (compute_agent_efficiency): 10 per-group fields with p95 nearest-rank

### Route 数据需求

28. GET / (dashboard): DashboardViewModel composition
29. GET /sessions: SessionsViewModel with anomaly enrichment
30. GET /sessions/{agent}/{session_id}: SessionDetail + source parse + rounds + anomaly + signals
31. GET /projects: ProjectsViewModel
32. GET /projects/{key}: ProjectDetailViewModel
33. GET /api/.../payload/{id}: Full untruncated payload JSON
34. GET /api/.../attribution/{round}/{call}/{kind}: Attribution JSON
35. GET /api/.../attribution/subagent/{sa_id}/{call_idx}/{kind}: Subagent attribution
36. GET /api/.../round/{index}: Round HTML fragment JSON
37. GET /api/.../bucket-detail/{round}/{key}: Bucket detail JSON

## QA Task 归属

| Task | 覆盖契约 |
|------|----------|
| QA-020 | F-*, Q-SUMMARY, typed query ports |
| QA-030 | get_session, list/count/aggregate sessions |
| QA-040 | dashboard/metrics/trend/project queries, M-AGGREGATE, M-AGENT-EFFICIENCY |
| QA-050 | session detail route, payload, attribution, round, bucket-detail APIs |
| QA-060 | D-* diagnostics, anomalies, percentiles, round signals |
| QA-070 | VM-* presenters, M-DERIVED, use case composition |
| QA-075 | 精简重复 SQL/DTO/assembler |
| QA-080 | parity/performance gate |
| QA-090 | stage closeout |

## 结论

- 所有 Python query/diagnostic 调用者已有归属
- 没有计划整块翻译 queries.py/routes.py
- 无 production 修改
