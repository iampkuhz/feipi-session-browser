## Goal

<一句话描述本次 session ingestion / token attribution 开发目标>

## Allowed scope

- 允许修改的模块和文件列表：
  - `java/core-domain/src/main/java/...`（NormalizedCall / Session / Message 数据模型）
  - `java/parser-*/src/main/java/...`（各平台 parser）
  - `java/<module>/src/test/java/...`（对应模块测试）
  - `java/<module>/build.gradle.kts`（如需）
  - `shared/SESSION_SCHEMA.md`（仅在任务明确要求时）

## Forbidden scope

- 不改 Java 产品代码中本任务无关的模块。
- 不改 hooks、quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删 required gates。
- 不新增 skip。

## Required reading

- `shared/SESSION_SCHEMA.md` — 规范化会话 schema 契约。
- `skills/authoring/feipi-session-ingestion-dev/references/architecture.md` — ingestion pipeline 架构。
- 相邻测试文件 — 只读与当前变更直接相关的测试。

## Validation

```bash
./scripts/session-browser.sh test
python scripts/quality/check_java_module_boundaries.py
```

按需追加：

```bash
python scripts/quality/check_manifest.py
python scripts/quality/run_required_quality_gates.py
```

## Expected output

- 改动的模块列表。
- Token 归因影响（如有）。
- 向后兼容性说明。
- 门禁运行结果。
- 后续风险或 TODO。
