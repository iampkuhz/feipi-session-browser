## Goal

<一句话描述本次 Java 功能研发目标>

## Allowed scope

- 允许修改的模块和文件列表：
  - `java/<module>/src/main/java/...`
  - `java/<module>/src/test/java/...`
  - `java/<module>/build.gradle.kts`（如需）

## Forbidden scope

- 不改 Java 产品代码中本任务无关的模块。
- 不改 hooks、quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删除任务范围外的 Gate。
- 不新增 skip。

## Required reading

- `config/architecture/java-modules.yaml` — 目标模块的边界规则。
- `java/<module>/build.gradle.kts` — 模块依赖。
- 相邻测试文件 — 只读与当前变更直接相关的测试。

## Validation

```bash
./scripts/session-browser.sh test
./gradlew check
```

按需追加：

```bash
python3 scripts/gates/cli.py run --mode incremental
```

`--mode full` 仅用于发布、周期审计或大迁移，不作为普通提交或交接的默认模式。

## Expected output

- 改动的 Java 模块列表。
- 模块依赖方向变化（如有）。
- 门禁运行结果。
- 后续风险或 TODO。
