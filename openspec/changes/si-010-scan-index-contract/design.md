# SI-010: Scan/Index 行为清单、Schema 契约与模块拓扑

## Stage
S3 -- Java Scan + SQLite Index

## Goal
审计 ~1,608 行 scanners.py、schema.py、writers.py、CLI scan/serve，冻结状态机和数据库契约，不创建空模块。

## Boundary
scan-index.contract

## Owner Before
Python scan/index (scanners.py, schema.py, writers.py, CLI)

## Owner After
contract frozen -- 所有行为、schema、模块拓扑已归类到 SI task

## Fallback
forbidden

## Kind
PLAN

## Allowed Files
- openspec/changes/**
- docs/acceptance-contracts/**
- tmp/java-migration-run/**

## Forbidden Files
- java/**/src/main/**
- src/session_browser/**
- scripts/session-browser.sh

---

## 1. 行为枚举 -- 全量扫描/索引生命周期

### 1.1 full_scan (scanners.py:841-1184)

| 步骤 | 行为 | 写路径 | trust boundary |
|------|------|--------|----------------|
| 1 | `_sync_source_data_dirs()` 刷新环境变量 | 无 | config adapter |
| 2 | `init_schema(conn)` DROP + CREATE | sessions, scan_log, index_metadata, session_artifacts | migration manager |
| 3 | `INSERT INTO scan_log` mode='full', status='running' | scan_log | scan lifecycle |
| 4 | Claude: `parse_history()` -> 去重 -> `_locate_claude_session_file()` | 无 | source adapter |
| 5 | Claude: `_summary_from_current_artifact()` 尝试复用 | 无 | artifact reader |
| 6 | Claude: `parse_session_detail()` 解析 JSONL | 无 | source adapter |
| 7 | Claude: `upsert_session()` 写入 sessions 行 | sessions | repository boundary |
| 8 | Claude: `_collect_batch_request()` 收集 Java batch 请求 | 无 | batch collector |
| 9 | Codex: `read_threads_db()` + `parse_session_index()` 预加载 | 无 | source adapter |
| 10 | Codex: 同样 upsert + collect batch | sessions | repository boundary |
| 11 | Qoder: `_discover_sessions()` + `_discover_cache_sessions()` | 无 | source adapter |
| 12 | Qoder: 同样 upsert + collect batch | sessions | repository boundary |
| 13 | `_finalize_scan()`: `execute_java_normalized_batch()` | session_artifacts | artifact writer (Java) |
| 14 | `_normalize_qoder_cache_projects()` 规范化 project_key | sessions | post-scan fixup |
| 15 | `UPDATE scan_log` status='done' | scan_log | scan lifecycle |

状态机: `running -> done`

### 1.2 incremental_scan (scanners.py:1190-1608)

| 步骤 | 行为 | 写路径 | trust boundary |
|------|------|--------|----------------|
| 1 | `ensure_session_artifacts_schema()` | session_artifacts | migration manager |
| 2 | `INSERT INTO scan_log` mode='incremental' | scan_log | scan lifecycle |
| 3 | 加载已有 sessions 的 file_mtime/file_path/ended_at | 无 | read query |
| 4 | Claude: mtime 比较 -> skip unchanged | 无 | fingerprint check |
| 5 | Claude: path relocation (moved files) | 无 | source adapter |
| 6 | Claude: `max_age_seconds` 窗口过滤 | 无 | tier filter |
| 7 | Claude: 仅 parse changed/new -> upsert + batch | sessions | repository boundary |
| 8 | Codex: `_delete_indexed_sessions()` 清除 subagent 行 | sessions, session_artifacts | delete/prune |
| 9 | Codex: 同样 mtime/path 检查 -> upsert | sessions | repository boundary |
| 10 | Qoder: 同样 mtime/path + cache canonical map -> upsert | sessions | repository boundary |
| 11 | `_finalize_scan()`: batch + qoder normalize + scan_log done | 同 full | 同上 |

状态机: 每个 session 候选 `unchanged | changed | new | retryable`

### 1.3 startup_scan (cli.py:886-912)

| 行为 | 写路径 | trust boundary |
|------|--------|----------------|
| `incremental_scan(max_age_seconds=2*3600)` | sessions | scan lifecycle |
| `_scan_lock('startup incremental scan', blocking=False)` | scan.lock | cross-process lock |
| 锁冲突时跳过，不阻塞 serve 启动 | 无 | graceful skip |

### 1.4 hot/warm tier (cli.py:953-1059)

`_BackgroundScanner` 类:
- **hot tier**: `hot_seconds=30*60` (30 min), `hot_interval=30s`
- **warm tier**: `warm_seconds=24*3600` (24h), `warm_interval=5*60` (5 min)
- **cold**: 不由 background 管理，需手动 full scan
- `_scan_lock('background incremental scan', blocking=False)` 非阻塞
- 锁冲突时更新时间戳跳过本轮
- daemon thread, serve 退出自动终止

### 1.5 delete (scanners.py:106-134)

`_delete_indexed_sessions()`:
- 先 `DELETE FROM session_artifacts WHERE session_key = ?`
- 再 `DELETE FROM sessions WHERE session_key = ?`
- 调用方: incremental scan 中 Codex subagent 清理

### 1.6 rename / path relocation (scanners.py:1296-1324, 1404-1419, 1526-1543)

- 三个 agent 均有 relocate 逻辑: stored_path 不存在时用 `_locate_*_session_file()` 重新查找
- 新路径存在且不同时标记 `path_relocated = True`
- 即使 mtime 未变也更新 file_path 行
- 不涉及 session_key 变更，仅 file_path/file_mtime 更新

### 1.7 repair (writers.py:345-411)

`repair_artifact_associations()`:
- 遍历 session_artifacts 行
- `validate_artifact_row()`: 存在性 -> 可读性 -> JSON 解析 -> size 一致 -> hash 校验
- ok: 更新 validation_status
- missing/corrupt: 删除 DB 行（下次 scan 重建）
- 幂等: 重复调用不改变正确结果

### 1.8 lock (cli.py:267-316)

`_scan_lock()`:
- 使用 `fcntl.flock(LOCK_EX | LOCK_NB)` OS 级文件锁
- lock file: `INDEX_DIR / 'scan.lock'`
- blocking 模式: 等待到 `timeout_seconds`
- 非阻塞: 立即抛 `ScanLockUnavailable`
- 写入 owner 标签用于诊断
- 退出 context 时 `LOCK_UN` 释放

### 1.9 cancel (cli.py:564-583)

`cmd_scan` 中:
- `_find_running_scan_pid()` 检测已有 scan 进程
- 交互式询问或 `--force` 自动 kill
- `_kill_process(pid)` 发送 SIGTERM
- 非交互式 `--force` 模式下自动 kill + 等待 1s

---

## 2. 冻结 Schema 契约

### 2.1 sessions 表

```sql
CREATE TABLE sessions (
    session_key TEXT PRIMARY KEY,                    -- "{agent}:{session_id}"
    agent TEXT NOT NULL CHECK(agent <> ''),           -- claude_code | codex | qoder
    session_id TEXT NOT NULL CHECK(session_id <> ''),
    title TEXT NOT NULL DEFAULT '',
    project_key TEXT NOT NULL CHECK(project_key <> ''),
    project_name TEXT NOT NULL DEFAULT '',
    cwd TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',              -- ISO 8601
    ended_at TEXT NOT NULL CHECK(ended_at <> ''),     -- ISO 8601
    duration_seconds REAL NOT NULL DEFAULT 0,
    model_execution_seconds REAL NOT NULL DEFAULT 0,
    tool_execution_seconds REAL NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    git_branch TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    user_message_count INTEGER NOT NULL DEFAULT 0,
    assistant_message_count INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    fresh_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    failed_tool_count INTEGER NOT NULL DEFAULT 0,
    subagent_instance_count INTEGER NOT NULL DEFAULT 0,
    indexed_at REAL NOT NULL DEFAULT 0,               -- Unix epoch
    file_mtime REAL NOT NULL DEFAULT 0,               -- source file mtime
    file_path TEXT NOT NULL DEFAULT ''                 -- source JSONL path
);
```

索引:
- `idx_sessions_project ON sessions(project_key)`
- `idx_sessions_agent ON sessions(agent)`
- `idx_sessions_ended_at ON sessions(ended_at DESC)`
- `idx_sessions_model ON sessions(model)`
- `idx_sessions_title ON sessions(title)`

版本策略: `_CURRENT_SESSION_COLUMNS` 集合 (cli.py:637-665) 用于 `_missing_current_session_columns()` 检测。缺失列时自动 full rebuild。

### 2.2 scan_log 表

```sql
CREATE TABLE scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,        -- Unix epoch
    finished_at REAL,                -- Unix epoch, NULL while running
    claude_count INTEGER DEFAULT 0,
    codex_count INTEGER DEFAULT 0,
    qoder_count INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'full',        -- 'full' | 'incremental'
    status TEXT DEFAULT 'running'    -- 'running' | 'done'
);
```

### 2.3 index_metadata 表

```sql
CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0   -- Unix epoch
);
```

已知 key:
- `scan_logic_version` (SCAN_LOGIC_VERSION = 4)

### 2.4 session_artifacts 表

```sql
CREATE TABLE session_artifacts (
    session_key TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    source_mtime REAL NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL DEFAULT 0,      -- Unix epoch
    updated_at REAL NOT NULL DEFAULT 0,      -- Unix epoch
    content_hash TEXT NOT NULL DEFAULT '',    -- SHA-256
    validation_status TEXT NOT NULL DEFAULT '', -- ok | stale | corrupt | missing | ''
    PRIMARY KEY(session_key, artifact_type),
    FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);
```

索引:
- `idx_session_artifacts_type ON session_artifacts(artifact_type)`
- `idx_session_artifacts_path ON session_artifacts(path)`

已知 artifact_type: `normalized_session_json`

migration 策略: `_migrate_artifact_columns()` 通过 `PRAGMA table_info` 检测后 `ALTER TABLE ADD COLUMN` 补齐。

### 2.5 SQLite PRAGMA

- `journal_mode = WAL`
- `busy_timeout = 30000` (30s)
- `foreign_keys = ON`
- `sqlite3.connect(timeout=30.0)`

### 2.6 版本策略

- `SCAN_LOGIC_VERSION = 4` -- 硬编码整数
- CLI `_decide_scan_mode()` 在版本不匹配时自动 full rebuild (需 env gate 开启)
- `init_schema()` 采用 DROP + CREATE 全量重建
- 列变更通过 `_CURRENT_SESSION_COLUMNS` 集合检测缺失

---

## 3. 模块拓扑设计

```
scan-engine          index-sqlite          application
+------------------+ +------------------+ +------------------+
| full_scan        | | schema.py        | | CLI cmd_scan     |
| incremental_scan | | writers.py       | | CLI cmd_serve    |
| file locators    | | queries.py       | | _BackgroundScanner|
| batch collector  | | metrics.py       | | _scan_lock       |
| artifact reuse   | | anomalies.py     | | _decide_scan_mode|
| qoder normalize  | | diagnostics.py   | |                  |
|                  | | percentiles.py   | |                  |
+------------------+ +------------------+ +------------------+
```

### 3.1 scan-engine (SI-050 ~ SI-080)

Java 接管:
- 源文件发现 (Claude/Codex/Qoder)
- mtime fingerprint 状态机
- normalized artifact 生产 (Java batch, 已在 S2C 完成)
- session row 映射和 batch write
- Qoder cache project key 规范化
- 状态机: unchanged / changed / new / retryable

### 3.2 index-sqlite (SI-020 ~ SI-040)

Java 接管:
- SQLite connection factory (WAL, busy_timeout, foreign_keys)
- schema init 和 migration
- session row upsert (ON CONFLICT)
- session_artifacts upsert + repair
- scan_log 记录
- index_metadata 读写
- query 接口 (list/filter/stats/dashboard)

### 3.3 application (SI-100)

Java 接管:
- CLI scan command (auto/full/incremental)
- scan.lock 跨进程锁
- _BackgroundScanner tiered 调度
- startup scan
- cancel/force kill

---

## 4. Python Symbol 归属

### 4.1 scanners.py

| Symbol | 行号 | 归属 |
|--------|------|------|
| `_runtime_config()` | 54 | SI-100 (application config reload) |
| `_sync_source_data_dirs()` | 68 | SI-050 (source discovery) |
| `_commit_periodically()` | 91 | SI-030 (transaction management) |
| `_delete_indexed_sessions()` | 106 | SI-070 (delete/prune state machine) |
| `_locate_claude_session_file()` | 140 | SI-050 (Claude source discovery) |
| `_locate_codex_session_file()` | 176 | SI-050 (Codex source discovery) |
| `_locate_qoder_session_file()` | 216 | SI-050 (Qoder source discovery) |
| `_summary_from_current_artifact()` | 266 | SI-040 (artifact -> row mapping) |
| `_summary_from_normalized_artifact()` | 305 | SI-040 (artifact -> row mapping) |
| `_summary_payload()` | 413 | SI-040 (summary -> artifact fields) |
| `_summary_count()` | 446 | SI-040 (counter extraction) |
| `_duration_seconds()` | 466 | SI-040 (duration calculation) |
| `_int_or_zero()` | 490 | SI-040 (type coercion) |
| `_float_or_zero()` | 511 | SI-040 (type coercion) |
| `_build_codex_normalized_for_scan()` | 531 | SI-050 (Codex artifact build) |
| `_index_dir_from_connection()` | 569 | SI-030 (connection -> path) |
| `_normalize_qoder_cache_projects()` | 597 | SI-050 (Qoder post-scan fixup) |
| `_process_full_scan_batch_results()` | 658 | SI-050 (batch result processing) |
| `_collect_batch_request()` | 745 | SI-050 (batch request collection) |
| `_finalize_scan()` | 781 | SI-050 (scan finalization) |
| `full_scan()` | 841 | SI-050 (Java full scan engine) |
| `incremental_scan()` | 1190 | SI-060 (Java incremental scan) |

### 4.2 schema.py

| Symbol | 行号 | 归属 |
|--------|------|------|
| `TIER_HOT_SECONDS` | 18 | SI-080 (tier config) |
| `TIER_HOT_INTERVAL` | 19 | SI-080 (tier config) |
| `TIER_WARM_SECONDS` | 20 | SI-080 (tier config) |
| `TIER_WARM_INTERVAL` | 21 | SI-080 (tier config) |
| `SCAN_LOGIC_VERSION` | 23 | SI-020 (schema version) |
| `SCAN_LOGIC_VERSION_KEY` | 24 | SI-020 (schema version) |
| `INDEX_METADATA_SCHEMA_SQL` | 27 | SI-020 (schema DDL) |
| `SESSION_ARTIFACTS_SCHEMA_SQL` | 35 | SI-020 (schema DDL) |
| `_ARTIFACT_MIGRATION_COLUMNS` | 61 | SI-020 (migration) |
| `_migrate_artifact_columns()` | 67 | SI-020 (migration) |
| `_get_connection()` | 88 | SI-030 (connection factory) |
| `ensure_session_artifacts_schema()` | 114 | SI-020 (schema init) |
| `ensure_index_metadata_schema()` | 128 | SI-020 (schema init) |
| `get_index_metadata()` | 140 | SI-020 (metadata read) |
| `set_index_metadata()` | 161 | SI-020 (metadata write) |
| `get_stored_scan_logic_version()` | 186 | SI-020 (version read) |
| `set_stored_scan_logic_version()` | 201 | SI-020 (version write) |
| `init_schema()` | 217 | SI-020 (full schema rebuild) |

### 4.3 writers.py

| Symbol | 行号 | 归属 |
|--------|------|------|
| `upsert_session()` | 20 | SI-040 (session row mapping + write) |
| `upsert_session_artifact()` | 112 | SI-040 (artifact row write) |
| `_ASSOCIABLE_STATUSES` | 186 | SI-040 (association guard) |
| `associate_verified_artifact()` | 189 | SI-040 (verified association) |
| `associate_batch_results()` | 240 | SI-040 (batch association) |
| `_VALID_STATUSES` | 283 | SI-070 (repair status enum) |
| `validate_artifact_row()` | 286 | SI-070 (artifact integrity check) |
| `repair_artifact_associations()` | 345 | SI-070 (idempotent repair) |
| `safe_upsert_after_bridge()` | 414 | SI-040 (safe bridge upsert) |
| `_row_to_summary()` | 457 | SI-040 (row -> domain mapping) |

### 4.4 indexer.py (facade)

所有 re-export 按目标模块归属，indexer.py 本身 SI-100 管理 facade 结构。

### 4.5 CLI scan/serve

| Symbol | 行号 | 归属 |
|--------|------|------|
| `ScanLockUnavailable` | 86 | SI-100 (scan lock exception) |
| `_scan_lock()` | 267 | SI-080 (cross-process lock) |
| `_scan_lock_timeout_seconds()` | 207 | SI-100 (config) |
| `_read_scan_lock_holder()` | 230 | SI-080 (lock diagnostics) |
| `_write_scan_lock_holder()` | 246 | SI-080 (lock owner write) |
| `_find_running_scan_pid()` | 318 | SI-100 (cancel detection) |
| `_kill_process()` | 354 | SI-100 (cancel kill) |
| `_decide_scan_mode()` | 476 | SI-100 (scan mode decision) |
| `_table_exists()` | 514 | SI-020 (schema detection) |
| `_missing_current_session_columns()` | 531 | SI-020 (schema detection) |
| `cmd_scan()` | 547 | SI-100 (scan CLI entry) |
| `cmd_serve()` | 802 | SI-100 (serve CLI entry) |
| `_BackgroundScanner` | 953 | SI-080 (tiered background scan) |
| `cmd_stop()` | 1062 | SI-100 (stop CLI entry) |

### 4.6 queries.py

| Symbol | 行号 | 归属 |
|--------|------|------|
| `get_session()` | 16 | DO_NOT_MIGRATE (Python Web 只读, S5 退休) |
| `list_sessions()` | 38 | DO_NOT_MIGRATE |
| `count_sessions()` | 117 | DO_NOT_MIGRATE |
| `get_sessions_list_aggregate()` | 167 | DO_NOT_MIGRATE |
| `get_project_stats()` | 230 | DO_NOT_MIGRATE |
| `count_projects()` | 292 | DO_NOT_MIGRATE |
| `list_projects()` | 322 | DO_NOT_MIGRATE |
| `get_dashboard_stats()` | 448 | DO_NOT_MIGRATE |
| `get_trend_data()` | 502 | DO_NOT_MIGRATE |
| `get_prompt_activity_trend()` | 576 | DO_NOT_MIGRATE |
| `list_agents()` | 640 | DO_NOT_MIGRATE |
| `list_model_stats()` | 675 | DO_NOT_MIGRATE |

注意: queries.py 的 DO_NOT_MIGRATE 指本 stage 不迁移。这些 query 将在 S5 (Web/Query 切换) 阶段迁移。

### 4.7 辅助模块

| Module | 归属 | 说明 |
|--------|------|------|
| metrics.py | DO_NOT_MIGRATE (S3) | Web dashboard metric queries，S5 迁移 |
| anomalies.py | DO_NOT_MIGRATE (S3) | Web anomaly detection，S5 迁移 |
| diagnostics.py | DO_NOT_MIGRATE (S3) | Web parse diagnostics，S5 迁移 |
| percentiles.py | DO_NOT_MIGRATE (S3) | Web threshold computation，S5 迁移 |

---

## 5. 状态机冻结

### 5.1 scan_log 状态机

```
running -> done
```

mode: `full | incremental`

### 5.2 session 候选状态机 (incremental)

```
candidate -> unchanged (mtime <= stored, skip)
           -> changed (mtime > stored, reparse)
           -> new (not in existing, parse)
           -> retryable (parse failed, next scan retry)
```

### 5.3 artifact validation_status 状态机

```
'' -> ok (verified write)
   -> missing (file gone)
   -> corrupt (read/JSON/size/hash mismatch)
   -> stale (source changed, not yet regenerated)
ok -> stale (source mtime changed)
ok -> missing (file deleted)
ok -> corrupt (file corrupted)
missing | corrupt -> deleted (repair removes row)
```

### 5.4 scan lock 状态机

```
unlocked -> locked (fcntl.flock LOCK_EX)
locked -> unlocked (LOCK_UN or process exit)
```

blocking mode: `unlocked -> waiting -> locked | timeout -> ScanLockUnavailable`

### 5.5 tier 调度状态机

```
serve started -> background scanner daemon
  hot: now - last_hot >= hot_interval -> incremental_scan(max_age=hot_seconds)
  warm: now - last_warm >= warm_interval -> incremental_scan(max_age=warm_seconds)
  cold: not managed (manual full scan)
```

---

## 6. 校验放置

| 校验条件 | 唯一位置 | 下游行为 |
|----------|----------|----------|
| CLI 参数 (--full/--incremental/--agent) | CLI adapter (`cmd_scan`) | typed scan config |
| scan.lock 可用性 | `_scan_lock()` | 抛 ScanLockUnavailable |
| SQLite PRAGMA 配置 | connection factory (`_get_connection`) | 下游信任连接 |
| schema 完整性 | `init_schema()` / `_table_exists()` | query/writer 使用已验证 schema |
| session_key 格式 | `upsert_session()` DB constraint | application 信任 typed key |
| artifact 文件完整性 | `validate_artifact_row()` | repair 基于结果操作 |
| bridge result status | `associate_verified_artifact()` | 只有 WRITTEN/UNCHANGED 写入 |
| source file mtime | incremental_scan 指纹检查 | 下游信任 fingerprint 结果 |
| normalized JSON 可解析 | `read_normalized_session_artifact()` | artifact reuse 信任解析结果 |

无重复校验: 每个条件只在一个 trust boundary 校验一次。

---

## 7. Acceptance Criteria

- [x] 所有写路径和状态转换已归类到具体 SI task
- [x] 没有把 scanners.py 整块翻译计划
- [x] schema contract 有 fixture/test owner (SI-020)
- [x] 无 production 实现修改
