# 数据索引模块 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | SQLite 索引器（全量/增量扫描、查询接口） |
| 关联源码 | `src/session_browser/index/indexer.py` |
| 关联测试 | `tests/index/` 下 12 个文件（81 测试函数） |
| 主要风险 | 增量扫描遗漏变更文件；全量/增量结果不一致；坏 JSON 文件污染索引 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| DATA-INDEX-001 | P0 | data | 全量扫描写入所有 agent 会话到 SQLite | 调用 `full_scan(verbose=True)`，查询 sessions 表 | claude/codex/qoder sessions 均有记录，session_key 格式为 `{agent}:{session_id}` | pytest | — | `tests/index/test_full_scan_fixture.py` |
| DATA-INDEX-002 | P0 | data | 增量扫描仅重解析 mtime 变更的文件 | 修改一个 JSONL 文件 mtime 后调用 `incremental_scan` | 统计中 `skipped` 包含未变更文件数，`claude_count + codex_count + qoder_count` 仅含变更数 | pytest | — | `tests/index/test_incremental_scan.py` |
| DATA-INDEX-003 | P0 | data | 全量与增量扫描结果一致性 | 先全扫描，再增量扫描（无文件变更），比较两次结果 | 两次扫描后 sessions 表的 COUNT(*) 和各字段值一致 | pytest | — | `tests/index/test_full_vs_incremental_consistency.py` |
| DATA-INDEX-004 | P0 | data | 新文件场景：增量扫描发现新 session | 新增一个 JSONL 文件后调用 `incremental_scan` | 统计中 `new_count >= 1`，新 session 出现在 sessions 表 | pytest | — | `tests/index/test_new_file_scenario.py` |
| DATA-INDEX-005 | P0 | data | 文件修改场景：增量扫描重解析变更 session | 修改已有 JSONL 内容并更新 mtime | 对应 session 的 title/user_message_count 等字段已更新 | pytest | — | `tests/index/test_modified_file_scenario.py` |
| DATA-INDEX-006 | P0 | data | 坏 JSON 隔离：损坏 JSONL 不影响其他 session 索引 | 放置含坏 JSON 行的 JSONL 文件 | 坏文件 session 标记 parse_diagnostics 警告，其他 session 正常索引 | pytest | — | `tests/index/test_bad_json_isolation.py` |
| DATA-INDEX-007 | P1 | data | 文件删除后索引一致性 | 删除已索引的 JSONL 文件后运行增量扫描 | 对应 session 仍保留在索引中（历史数据不丢弃），或根据策略标记 | pytest | — | `tests/index/test_delete_file_contract.py` |
| DATA-INDEX-008 | P1 | data | Qoder canonical 去重：cache 与 projects 不重复索引 | projects/ 放 full UUID，cache/ 放可映射的 short ID | 增量扫描后，去重后的 session 数量等于 projects/ 独有 + cache/ 独有 | pytest | — | `tests/index/test_qoder_canonical_dedup.py` |
| DATA-INDEX-009 | P1 | data | Qoder 增量更新（projects/ + cache/projects/） | 同时修改 projects/ 和 cache/ 下的 JSONL 文件 | 两个来源的 session 都被重解析，qoder_count 覆盖两者 | pytest | — | `tests/index/test_qoder_incremental_update.py` |
| DATA-INDEX-010 | P1 | data | Qoder 定位器展开（文件查找） | 放置 session 文件在不同层级目录 | `_locate_qoder_session_file` 返回正确路径，支持 direct match 和递归搜索 | pytest | — | `tests/index/test_qoder_locator_expansion.py` |
| DATA-INDEX-011 | P1 | data | Qoder 项目路径契约（URL-decode） | 构造 URL-encoded 项目目录名 | `_url_decode_path` 正确解码，"%" 编码字符转为 "/" | pytest | — | `tests/index/test_qoder_project_path_contract.py` |
| DATA-INDEX-012 | P1 | data | 会话筛选查询（agent/project/model/title_like） | 调用 `list_sessions` 带不同过滤参数 | 返回的 session 数量与过滤条件匹配，WHERE 子句正确组合 | pytest | — | `tests/index/test_sessions_filters.py` |
