# SI-020 Design: SQLite Schema、版本与可回滚 Migration

## 1. 目标

实现 Java schema migration 基础设施：
- schema version 独立于 scan logic version
- 每个 migration 原子事务，失败回滚
- SQL 作为版本控制资源，不散落在 Java 代码中
- 幂等执行，重复调用安全
- 覆盖空 DB、当前 DB、旧列缺失、重复 migration、失败回滚

## 2. 架构

### 2.1 类型定义

| 类型 | 职责 | 消费者 |
|------|------|--------|
| `SchemaVersion` record | schema 版本号，独立于 scan logic version | MigrationRunner, IndexSchema |
| `Migration` record | 单条 migration 定义：版本号、描述、SQL 资源路径 | MigrationRunner |
| `MigrationRunner` | 幂等 migration 执行器：追踪表、事务控制、回滚 | IndexSchema |
| `IndexSchema` | schema 入口：migration 注册、表结构验证、缺失列修复 | SI-030 (connection), SI-040 (writer) |

### 2.2 SQL 资源管理

SQL 文件存放在 `src/main/resources/sql/`，命名规范 `V{NNN}__<描述>.sql`。

- `V001__initial_schema.sql` -- 初始 schema（sessions, scan_log, index_metadata, session_artifacts）
- `Migration.loadSql()` 从 classpath 加载 SQL 内容
- `Migration.allMigrations()` 注册全部 migration，按版本号升序

### 2.3 Migration 执行流程

```
ensureSchema(conn)
├── MigrationRunner.applyAll(conn)
│   ├── 创建 schema_migrations 追踪表（IF NOT EXISTS）
│   ├── 查询已应用版本
│   └── 对每个未应用的 migration:
│       ├── BEGIN（关闭 autoCommit）
│       ├── 执行 SQL
│       ├── INSERT INTO schema_migrations
│       ├── COMMIT
│       └── 失败时 ROLLBACK + 抛出异常
└── IndexSchema.repairMissingColumns(conn)
    └── 检测 sessions 表缺失列 → ALTER TABLE ADD COLUMN
```

### 2.4 Schema 与 Scan Logic Version 分离

- `schema_migrations` 表追踪 schema version（表结构变化）
- `index_metadata` 表追踪 scan_logic_version（扫描逻辑和数据格式变化）
- 两者独立演进，互不依赖

### 2.5 旧数据库升级

从 Python 旧数据库升级时：
1. V001 使用 `CREATE TABLE IF NOT EXISTS`，对已存在的表不报错
2. `repairMissingColumns()` 检测缺失列并用 `ALTER TABLE ADD COLUMN` 补充
3. `schema_migrations` 记录 V1 为已应用

## 3. 校验放置

| 校验 | 位置 | 理由 |
|------|------|------|
| schema 版本追踪 | MigrationRunner | migration manager 边界 |
| 表结构完整性 | IndexSchema.validateSchema | schema 入口，供下游信任 |
| 列名/类型定义 | IndexSchema.SESSIONS_COLUMNS | 单一事实来源 |
| PRAGMA 配置 | SqliteTestHelper / SI-030 ConnectionFactory | 连接层职责 |

## 4. 测试覆盖

| 场景 | 测试 | 文件 |
|------|------|------|
| 空 DB | MigrationRunnerTest.EmptyDatabase | index-sqlite |
| 当前 DB | MigrationRunnerTest.CurrentDatabase | index-sqlite |
| 旧列缺失 | IndexSchemaTest.MissingColumns | index-sqlite |
| 重复 migration | MigrationRunnerTest.DuplicateMigration | index-sqlite |
| 失败回滚 | MigrationRunnerTest.FailureRollback | index-sqlite |
| Schema 契约 | SchemaContractTest | contract-tests |
