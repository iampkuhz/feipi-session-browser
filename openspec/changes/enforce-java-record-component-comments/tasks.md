# Tasks: Enforce Java record component comments

Walk these tasks sequentially. Mark each checkbox with validation evidence when done.

## Phase 1: OpenSpec baseline

- [x] 1.1 创建并激活 `enforce-java-record-component-comments` change，补齐 proposal/design/tasks/spec delta。
  - Validation: `python3 scripts/openspec/validate_layout.py && python3 scripts/openspec/validate_schema.py && python3 scripts/openspec/validate_active_change.py --change-id enforce-java-record-component-comments`
  - Result: PASS；change proposal/design/tasks/spec delta 已创建，`tmp/active_change.json` 已指向本 change。

## Phase 2: Record component gate

- [x] 2.1 新增 record component Javadoc checker 和单元测试。
  - Validation: `.venv/bin/python -m pytest -q -W error tests/quality/test_check_java_record_component_javadocs.py`
  - Result: PASS，6 passed；新增覆盖类型注解位于 Javadoc 与 record 之间时的合法场景。

- [x] 2.2 将 `javaRecordComponentJavadocs` 接入 required `java-src` target 与根 Gradle `check`。
  - Validation: `.venv/bin/python -m pytest -q -W error tests/quality/test_quality_gate_runner.py tests/quality/test_run_required_quality_gates.py`；`./gradlew verifyJavaRecordComponentJavadocs --no-daemon`
  - Result: PASS；相关 pytest 与 Gradle task 均通过。

## Phase 3: Codex Stop routing

- [x] 3.1 修复 Codex Stop wrapper/共享 Stop runner 测试，保证缺少 session identity 时 dirty/untracked Java 文件 fail-closed 触发 `java-src`。
  - Validation: `.venv/bin/python -m pytest -q -W error tests/harness/test_agent_stop_check.py`
  - Result: PASS；新增测试覆盖 Codex Stop 缺少 session id 时 dirty Java 文件触发 `java-src`，并修复 `.codex/hooks/post_bash_guard.sh` executable bit。

## Phase 4: Existing Java records

- [x] 4.1 修复当前 Java 源码中 record 的中文类型说明和每个 component 的中文 `@param`。
  - Validation: `python3 scripts/quality/check_java_record_component_javadocs.py java`；`python3 scripts/quality/check_code_comment_language.py --policy config/technical-terms.json java`
  - Result: PASS；record component Javadoc 检查 0 违规，中文注释检查 `PASS: scanned 472 files with 8 workers`。

## Phase 5: Final gates

- [x] 5.1 运行 OpenSpec/harness validators 和本次 required quality gate。
  - Validation: `python3 scripts/openspec/validate_layout.py && python3 scripts/openspec/validate_schema.py && python3 scripts/openspec/validate_active_change.py --change-id enforce-java-record-component-comments && python3 scripts/harness/validate_harness_structure.py && python3 scripts/quality/run_required_quality_gates.py --change-id enforce-java-record-component-comments --changed-files '["java/index-sqlite/src/main/java/com/feipi/session/browser/index/sqlite/ProjectListSummaryRow.java"]'`
  - Result: PASS；`java-src` 与 `scan-script-smoke` target 均通过，artifact 位于 `tmp/quality/enforce-java-record-component-comments/`。
