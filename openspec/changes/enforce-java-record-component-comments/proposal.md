# Proposal: Enforce Java record component comments

## Problem

Java 质量门目前存在两个盲区：

- Checkstyle 只要求 `record` 类型本身存在 Javadoc，不要求 record header 中每个 component 都有 `@param` 说明。
- 中文注释检查器只校验已有注释是否以中文为主体，不校验缺失的 record component 文档。

因此 `ProjectListSummaryRow` 这类数据载体可以带一行英文类型注释、没有任何 component 说明，却仍通过局部 Java check。与此同时，Codex hook 的 changed-files evidence 在缺少 session identity 时不稳定，Stop 自动路由可能没有触发 `java-src` required gate，进一步放大了漏检风险。

## Scope

- 新增 Java record component Javadoc 门禁：扫描 `java/**/src/main/java/**/*.java`，要求每个 record component 在 record 类型 Javadoc 中有对应 `@param <name>`，且说明包含中文叙述。
- 将该门禁接入 Java source required target 和根项目 `check`，确保全量/required 场景都能运行。
- 为门禁添加单元测试，覆盖中文通过、缺失 `@param`、英文说明、空说明、多行/泛型/注解 component 等样例。
- 修复 Codex Stop 在缺失 session id 时不稳定记录 changed-files 的问题，使 dirty/untracked Java 文件能 fail-closed 触发 required gate。
- 修复当前新增/变更 record 的中文 Javadoc 违规，尤其是 API-first 改造引入的数据 record。

## Non-goals

- 不要求普通 class 字段逐字段 Javadoc；本次只覆盖 Java record component。
- 不改变产品运行时行为、Web API 响应结构或页面逻辑。
- 不把所有 JDK doclint missing 检查一次性打开，避免引入与本缺陷无关的大范围历史债务。
- 不提交 ignored 的 `tmp/` 运行 evidence。

## User impact

开发者修改或新增 Java record 时，必须为每个 component 写中文 `@param` 说明；Codex Stop/required gate 能更可靠地因为 Java 源码变更触发对应门禁，从而在 review 前暴露缺少属性注释和英文注释问题。

## Validation strategy

- `python3 scripts/openspec/validate_layout.py`
- `python3 scripts/openspec/validate_schema.py`
- `python3 scripts/openspec/validate_active_change.py --change-id enforce-java-record-component-comments`
- `python3 scripts/harness/validate_harness_structure.py`
- `.venv/bin/python -m pytest -q -W error tests/quality/test_check_java_record_component_javadocs.py tests/quality/test_quality_gate_runner.py tests/quality/test_run_required_quality_gates.py tests/harness/test_agent_stop_check.py`
- `python3 scripts/quality/check_java_record_component_javadocs.py java`
- `./gradlew verifyJavaRecordComponentJavadocs --no-daemon`
- `python3 scripts/quality/run_required_quality_gates.py --change-id enforce-java-record-component-comments --changed-files '["java/index-sqlite/src/main/java/com/feipi/session/browser/index/sqlite/ProjectListSummaryRow.java"]'`
