# Design: 优化 Java module 拓扑与目录层级

## Current state

`settings.gradle.kts` include 了 18 个 Java 相关子项目，其中 `source-json`、`source-claude`、`source-codex`、`source-qoder` 是小型 source 实现模块；`data` 仅包含 normalized batch protocol/runner；`query-api` 仅包含查询 DTO/filter/sort 类型并被 `application` 和 `web` 同时依赖。`config/architecture/java-modules.yaml` 已将 `data`、`web`、`app-cli` 的多条依赖标记为 transition dependency，并预留了未 include 的 `:java:sources`。

## Proposed approach

1. 新增/启用 `:java:sources` module：移动 `source-json`、`source-claude`、`source-codex`、`source-qoder` 源码与测试，保留原 package 名，删除旧 module include 与 build 文件。
2. 将 `query-api` 源码移动进 `:java:application`，保留 `com.feipi.session.browser.query.api` package，更新 `application` 依赖和所有消费者依赖。
3. 将 `data` batch 源码移动进 `:java:app-cli`，保留或调整到 CLI batch package；删除 `:java:data` include 与 build 文件。
4. 将测试相关 module 从 Java 顶层迁入 `java/tests/` 子目录：`:java:tests:support` 作为测试工具库，`:java:tests:architecture` 作为架构守卫，`:java:tests:contracts` 作为跨模块契约测试。
5. 更新所有 Gradle project dependencies、`config/architecture/java-modules.yaml`、contract/architecture tests 中的模块拓扑预期。
6. 对大模块内部做低风险目录优化：仅移动 package 边界清晰的类，优先不改变公开类型名和协议字段；必要时更新 package 与 imports。

## Risks

- 大规模移动会触发 import、Javadoc link、Checkstyle 或 package-root 边界失败。
- 合并 `source-codex` 会让 `:java:sources` 携带 SQLite JDBC 依赖；当前整体发行可接受，但未来插件化需再拆。
- `query-api` 合入 `application` 后，application 成为查询契约类型的提供者，需避免 application 反向泄漏 web/CLI 关注点。
- 测试 module 改为嵌套 project path 后，质量门脚本、样例集成 task 和 API snapshot 都必须同步更新，否则会出现旧路径残留。

## Rollback

可按 Gradle module 粒度回滚：恢复旧 include/build 文件，将移动文件放回原目录，恢复 `config/architecture/java-modules.yaml` 旧 module 配置与依赖声明。

## Validation

- `python3 scripts/openspec/validate_layout.py`
- `python3 scripts/openspec/validate_schema.py`
- `python3 scripts/openspec/validate_active_change.py --change-id optimize-java-module-topology`
- `python3 scripts/harness/validate_harness_structure.py`
- `python3 scripts/quality/check_java_module_boundaries.py --fail-transition`
- `./gradlew check`
