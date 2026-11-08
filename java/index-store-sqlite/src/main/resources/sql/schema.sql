-- 当前发行索引的完整建表语句。仅用于空数据库。

-- session 索引主表：记录已解析的 session 行数据
CREATE TABLE sessions (
    session_key TEXT PRIMARY KEY,
    agent TEXT NOT NULL CHECK(agent <> ''),
    session_id TEXT NOT NULL CHECK(session_id <> ''),
    title TEXT NOT NULL DEFAULT '',
    project_key TEXT NOT NULL,
    project_name TEXT NOT NULL DEFAULT '',
    cwd TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    ended_at TEXT NOT NULL,
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
    file_path TEXT NOT NULL DEFAULT '',
    round_count INTEGER CHECK (round_count >= 0),
    llm_call_count INTEGER CHECK (llm_call_count >= 0),
    model_call_count INTEGER CHECK (model_call_count >= 0),
    content_measured INTEGER NOT NULL DEFAULT 0 CHECK (content_measured IN (0, 1)),
    user_message_measured INTEGER NOT NULL DEFAULT 0 CHECK (user_message_measured IN (0, 1)),
    assistant_message_measured INTEGER NOT NULL DEFAULT 0 CHECK (assistant_message_measured IN (0, 1)),
    fresh_input_token_precision TEXT NOT NULL DEFAULT 'unknown',
    cache_read_token_precision TEXT NOT NULL DEFAULT 'unknown',
    cache_write_token_precision TEXT NOT NULL DEFAULT 'unknown',
    output_token_precision TEXT NOT NULL DEFAULT 'unknown',
    token_estimation_method TEXT NOT NULL DEFAULT '',
    token_contains_estimated INTEGER NOT NULL DEFAULT 0,
    token_contains_unavailable INTEGER NOT NULL DEFAULT 0,
    token_contains_unknown INTEGER NOT NULL DEFAULT 1,
    timing_json TEXT NOT NULL DEFAULT '{}'
);

-- 扫描日志：记录每次 scan 生命周期
CREATE TABLE scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    claude_count INTEGER DEFAULT 0,
    codex_count INTEGER DEFAULT 0,
    qoder_count INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'full',
    status TEXT DEFAULT 'running',
    error_count INTEGER NOT NULL DEFAULT 0,
    failures_json TEXT NOT NULL DEFAULT '[]',
    processed_count INTEGER NOT NULL DEFAULT 0
);

-- 全局元数据：存储 scan_logic_version 等全局状态
CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL DEFAULT 0
);

-- session 制品关联：记录 session 的归一化制品路径和元数据
CREATE TABLE session_artifacts (
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

CREATE TABLE event_activity_coverage (
 session_key TEXT PRIMARY KEY,
 observedUserMessages INTEGER NOT NULL,
 undatedUserMessages INTEGER NOT NULL,
 supportedUsageEvents INTEGER NOT NULL,
 undatedUsageEvents INTEGER NOT NULL,
 unsupportedUsageEvents INTEGER NOT NULL
);
CREATE TABLE event_activity_days (
 session_key TEXT NOT NULL,
 epoch_day INTEGER NOT NULL,
 latest_event_timestamp TEXT NOT NULL,
 observed_user_messages INTEGER NOT NULL,
 PRIMARY KEY(session_key, epoch_day)
);
CREATE TABLE event_activity_tokens (
 session_key TEXT NOT NULL,
 day_key TEXT NOT NULL,
 component TEXT NOT NULL,
 reportedTokens INTEGER NOT NULL,
 reportedSamples INTEGER NOT NULL,
 estimatedSamples INTEGER NOT NULL,
 unavailableSamples INTEGER NOT NULL,
 unknownSamples INTEGER NOT NULL,
 mixedSamples INTEGER NOT NULL,
 PRIMARY KEY(session_key, day_key, component)
);

CREATE INDEX idx_sessions_project ON sessions(project_key);
CREATE INDEX idx_sessions_agent ON sessions(agent);
CREATE INDEX idx_sessions_ended_at ON sessions(ended_at DESC);
CREATE INDEX idx_sessions_model ON sessions(model);
CREATE INDEX idx_sessions_title ON sessions(title);
CREATE INDEX idx_session_artifacts_type ON session_artifacts(artifact_type);
CREATE INDEX idx_session_artifacts_path ON session_artifacts(path);
