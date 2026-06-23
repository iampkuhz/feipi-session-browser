-- V001: 初始 index schema（与 Python 版 schema.py 对齐）
-- 包含 sessions、scan_log、index_metadata、session_artifacts 四张表。
-- 索引在表创建后由 IndexSchema.ensureIndexes 补充，以支持旧列缺失修复场景。

-- session 索引主表：记录已解析的 session 行数据
CREATE TABLE IF NOT EXISTS sessions (
    session_key TEXT PRIMARY KEY,
    agent TEXT NOT NULL CHECK(agent <> ''),
    session_id TEXT NOT NULL CHECK(session_id <> ''),
    title TEXT NOT NULL DEFAULT '',
    project_key TEXT NOT NULL CHECK(project_key <> ''),
    project_name TEXT NOT NULL DEFAULT '',
    cwd TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    ended_at TEXT NOT NULL CHECK(ended_at <> ''),
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
    indexed_at REAL NOT NULL DEFAULT 0,
    file_mtime REAL NOT NULL DEFAULT 0,
    file_path TEXT NOT NULL DEFAULT ''
);

-- 扫描日志：记录每次 scan 生命周期
CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    claude_count INTEGER DEFAULT 0,
    codex_count INTEGER DEFAULT 0,
    qoder_count INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'full',
    status TEXT DEFAULT 'running'
);

-- 全局元数据：存储 scan_logic_version 等全局状态
CREATE TABLE IF NOT EXISTS index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0
);

-- session 制品关联：记录 session 的归一化制品路径和元数据
CREATE TABLE IF NOT EXISTS session_artifacts (
    session_key TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    source_mtime REAL NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(session_key, artifact_type),
    FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);
