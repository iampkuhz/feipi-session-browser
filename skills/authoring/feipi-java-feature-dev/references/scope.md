## 负责范围

- Java 产品模块的功能开发：`common`、`validation`、`core-domain`、`source-spi`、`sources`、`normalization-engine`、`index-api`、`index-store-sqlite`、`scan-engine`、`application`、`web`。
- CLI 入口：`java:app-cli`。
- Gradle 构建配置：`gradle/build-logic/`、各模块 `build.gradle.kts`。
- 测试代码：`java/<module>/src/test/`、`java:tests:support`、`java:tests:architecture`、`java:tests:contracts`。
- 模块边界配置：`config/architecture/java-modules.yaml`。

## 禁止范围

- 不改 Python 产品代码（`src/`）。
- 不改 OpenSpec 编排或 agent runtime 配置（属于其他 skill）。
- 不改 UI 模板渲染逻辑（属于 `feipi-session-detail-ui-dev`）。
- 不改 hooks、quality gate 脚本（除非任务明确要求）。
- 不改真实 session 数据、缓存、密钥、token、个人配置。

## 关键路径

1. `settings.gradle.kts` → 模块列表。
2. `config/architecture/java-modules.yaml` → 模块边界、allowedProjectDeps、transitionProjectDeps、packageRoots、forbiddenImports。
3. `java/<module>/build.gradle.kts` → 模块依赖。
4. `java/<module>/src/main/java/` → 生产代码。
5. `java/<module>/src/test/java/` → 测试代码。

## 常见误区

- 误以为可以直接 `import` 任意模块的类。实际有 forbiddenImports 和 allowedProjectDeps 约束。
- 误以为测试模块可以随意依赖生产模块。`java:tests:*` 有独立的依赖规则。
- 误用历史根模块路径 `:app-cli`。CLI 任务统一使用 `:java:app-cli`。

## 触发门禁

- `./scripts/session-browser.sh test`
- `./gradlew check`
- `python3 scripts/gates/cli.py --mode incremental`（普通提交或交接）
- `python3 scripts/gates/cli.py --mode full`（仅发布、周期审计或大迁移）
