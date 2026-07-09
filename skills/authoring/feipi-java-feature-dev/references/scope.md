## 负责范围

- Java 产品模块的功能开发：`core-domain`、`source-spi`、`sources`、`artifact-normalized`、`normalization-engine`、`index-sqlite`、`scan-engine`、`application`、`web`、`common`。
- CLI 入口：`app-cli`、`java:app-cli`。
- Gradle 构建配置：`build-logic/`、各模块 `build.gradle.kts`。
- 测试代码：`java/<module>/src/test/`、`java:tests:support`、`java:tests:architecture`、`java:tests:contracts`。
- API snapshot：`config/api-snapshots/`。
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
6. `config/api-snapshots/` → API 一致性快照。

## 常见误区

- 误以为可以直接 `import` 任意模块的类。实际有 forbiddenImports 和 allowedProjectDeps 约束。
- 误以为测试模块可以随意依赖生产模块。`java:tests:*` 有独立的依赖规则。
- 误以为 API 签名改了只需重新编译。需要更新 `config/api-snapshots/` 下的 snapshot。
- 误以为 `app-cli` 和 `java:app-cli` 是同一个模块。它们是不同的 Gradle 模块。

## 触发门禁

- `./scripts/session-browser.sh test`
- `python scripts/quality/check_java_module_boundaries.py`
- `python scripts/quality/check_java_api_snapshot.py`
- `python scripts/quality/run_required_quality_gates.py`
