# 数据源模块 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 数据源解析（Claude / Codex / Qoder） |
| 关联源码 | `src/session_browser/sources/claude.py`、`codex_session_source.py`、`qoder.py` |
| 关联测试 | `tests/backend/test_claude_source.py`、`test_codex_source.py`、`test_qoder_model_contract.py`、`test_qoder_token_estimation.py` |
| 主要风险 | 不同 agent 的 JSONL 事件格式差异导致解析失败；token 估算偏差；模型名解析不正确 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| DATA-SOURCE-001 | P0 | data | Claude JSONL 事件解析返回 SessionSummary | pytest 使用 fixture 的 JSONL 文件调用 `parse_session_detail` | `session_summary.agent == "claude_code"`、`session_summary.session_id` 非空、`user_message_count > 0` | pytest | — | 待补充 |
| DATA-SOURCE-002 | P0 | data | Claude assistant 消息合并（多 fragment 合并为一条） | 构造含 text/thinking/tool_use fragment 的 JSONL | `_assistant_records()` 返回的记录数等于独立 message id 数，usage 为 max 合并 | pytest | — | 待补充 |
| DATA-SOURCE-003 | P0 | data | Claude tool_result 失败检测启发式 | 传入含 "command not found"、"permission denied" 等 marker 的 tool result | `_tool_result_looks_failed()` 对运行时错误返回 True，对正常退出码返回 False | pytest | — | 待补充 |
| DATA-SOURCE-004 | P0 | data | Claude subagent 侧链文件解析 | 在 session 目录放置 subagents/*.jsonl | `parse_session_detail` 返回的 `subagent_runs` 非空，包含 agent_id/summary | pytest | — | 待补充 |
| DATA-SOURCE-005 | P0 | data | Codex session_index.jsonl 解析 | 读取 fixture session_index.jsonl | 返回 list，每个元素含 id/thread_name/updated_at | pytest | — | 待补充 |
| DATA-SOURCE-006 | P0 | data | Codex state_5.sqlite threads 表读取 | 读取 fixture SQLite 文件 | 返回 dict，key 为 thread id，含 title/cwd/model/rollout_path | pytest | — | 待补充 |
| DATA-SOURCE-007 | P0 | data | Codex session 文件层级查找 | 在 `sessions/{year}/{month}/day/` 下放置 rollout JSONL | `_find_session_file()` 返回正确的文件路径 | pytest | — | 待补充 |
| DATA-SOURCE-008 | P0 | data | Qoder 事件解析返回 SessionSummary | pytest 使用 fixture Qoder JSONL 调用 `parse_session_detail` | `session_summary.agent == "qoder"`、`session_summary.session_id` 非空、`user_message_count > 0` | pytest | — | 待补充 |
| DATA-SOURCE-009 | P0 | data | Qoder 模型名解析（多源 fallback） | 构造含 message.model / top-level model / metadata.model 的事件 | `_extract_qoder_model()` 按优先级返回 model，最终回退到 GUI 日志推断 | pytest | — | 待补充 |
| DATA-SOURCE-010 | P0 | data | Qoder token 估算（无 usage 时 byte-level 启发式） | 构造无 usage dict 的 Qoder 事件 | `_count_tokens()` 返回 `max(1, int(len(encoded)/3.5))`，`_estimate_tokens_from_events()` 区分有/无真实 usage | pytest | — | 待补充 |
| DATA-SOURCE-011 | P0 | data | Qoder short ID 与 full UUID canonical 映射 | 在 projects/ 放 full UUID，在 cache/projects/ 放 short prefix | `_build_canonical_id_map()` 正确映射唯一前缀匹配，模糊匹配不合并 | pytest | — | 待补充 |
| DATA-SOURCE-012 | P1 | data | Qoder cache 格式 session 解析（无 timestamp） | 读取 cache/projects/ 下的 cache 格式 JSONL | `_parse_cache_session()` 使用 file_mtime 作为 started_at/ended_at | pytest | — | 待补充 |
| DATA-SOURCE-013 | P1 | data | Qoder tool 执行 duration_ms 计算 | 构造含 tool_use 和 tool_result 时间戳的事件 | `ToolCall.duration_ms = result_ts - use_ts`，仅当 result_ts >= use_ts | pytest | — | 待补充 |
| DATA-SOURCE-014 | P1 | data | Claude history.jsonl 解析与 dedup | 读取含重复 sessionId 的 history.jsonl | `parse_history()` 返回去重后条目，保留最后一条 | pytest | — | 待补充 |
| DATA-SOURCE-015 | P1 | data | Claude 标题提取（command envelope 处理） | 传入含 `<command-message>/<command-args>` 的 display 字段 | `_extract_readable_title()` 返回 "spec-research · user-intent" 格式 | pytest | — | 待补充 |
