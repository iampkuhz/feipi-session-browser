# Tasks: 优化 Java module 拓扑与目录层级

Walk these tasks sequentially. Mark each checkbox with validation evidence when done.

## Phase 1: OpenSpec 与边界基线

- [x] 1.1 创建 OpenSpec change，并记录当前 module 拓扑与目标拓扑。
  - Validation: `python3 scripts/openspec/validate_layout.py`、`python3 scripts/openspec/validate_schema.py`、`python3 scripts/openspec/validate_active_change.py --change-id optimize-java-module-topology` 通过。

## Phase 2: Source module 合并

- [x] 2.1 启用 `:java:sources`，迁移 `source-json`、`source-claude`、`source-codex`、`source-qoder` 源码/测试并删除旧 module include。
  - Validation: `./gradlew :java:sources:test :java:sources:javadoc` 通过。

## Phase 3: Query/Application 合并

- [x] 3.1 将 `:java:query-api` 合入 `:java:application`，更新依赖、imports 与测试。
  - Validation: `./gradlew :java:application:test :java:web:test :java:tests:contracts:test` targeted run 中三项通过；`compileTestJava` 也通过。

## Phase 4: Data module 淘汰

- [x] 4.1 将 normalized batch protocol/runner 移入 `:java:app-cli` 并删除 `:java:data` module。
  - Validation: `./gradlew :java:app-cli:test` 复跑通过，targeted run 中 `:java:app-cli:cliSmokeTest` 通过。

## Phase 5: 目录层级优化与边界收敛

- [x] 5.1 优化大 module 内部 package/目录：CLI、application query API、index-sqlite、scan-engine、web 的职责分组。
  - Validation: `./gradlew spotlessApply` 已执行；最终由 `./gradlew check` 覆盖 `spotlessCheck`、Checkstyle、PMD。

- [x] 5.2 更新 `config/architecture/java-modules.yaml` 与相关契约测试，使 transition dependency 清零。
  - Validation: `python3 scripts/quality/check_java_module_boundaries.py --fail-transition` 通过，summary errors=0 warnings=0 infos=0。

## Phase 6: 测试 module 子目录分组

- [x] 6.1 将 `architecture-tests`、`contract-tests`、`test-support` 移入 `java/tests/` 子目录，并更新 Gradle project path、质量门脚本和模块边界配置。
  - Validation: 由 `./gradlew check --continue`、`python3 scripts/quality/check_java_module_boundaries.py --fail-transition` 和 required quality gates 覆盖。

## Phase 7: 全量验证

- [x] 7.1 运行 OpenSpec、harness、module boundary 与 Java 全量 required gates。
  - Validation: `python3 scripts/openspec/validate_layout.py`、`python3 scripts/openspec/validate_schema.py`、`python3 scripts/openspec/validate_active_change.py --change-id optimize-java-module-topology`、`python3 scripts/harness/validate_harness_structure.py`、`python3 scripts/quality/check_java_module_boundaries.py --fail-transition`、`python3 scripts/quality/check_java_api_snapshot.py --check --java-root java --snapshot config/api-snapshots/java-public-api.txt`、`./gradlew check --continue`、`.venv/bin/python scripts/quality/run_required_quality_gates.py --change-id optimize-java-module-topology --tier required --changed-files "$(cat /tmp/changed-files.json)"` 全部通过；`verifyNoSkippedJavaTests` 报告 1996 tests、0 failed、0 errored、0 skipped、0 aborted。
