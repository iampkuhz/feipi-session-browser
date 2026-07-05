# Design: Enforce Java record component comments

## Current state

- `config/checkstyle/checkstyle.xml` 的 `MissingJavadocType` 包含 `RECORD_DEF`，只能证明 record 有类型 Javadoc。
- `MissingJavadocMethod` 不覆盖 record component，也不要求 record 类型 Javadoc 中存在每个 component 的 `@param`。
- `scripts/quality/check_code_comment_language.py` 会对已有英文 Javadoc 报 `COMMENT_NOT_CHINESE_DOMINANT`，但不会发现缺失的 `@param`。
- `build-logic/src/main/kotlin/feipi.java-quality.gradle.kts` 显式使用 `Xdoclint:all,-missing`，JDK doclint 不会因为缺失 Javadoc/tags 失败。
- Codex wrappers 会调用共享 hook/Stop runner，但缺少 session id 时只落到 `codex/unknown`，changed-file evidence 为空时依赖 fail-closed dirty 状态；当前用户观察到 required target 可能未被触发。

## Proposed approach

1. 新增 `scripts/quality/check_java_record_component_javadocs.py`：
   - 词法清理字符串和普通注释，保留 Javadoc 起止位置。
   - 识别顶层或嵌套 `record Name(...)` header，按括号层级拆分 component。
   - 对每个 component 提取最终标识符名称，兼容注解、泛型、数组、varargs。
   - 查找 record 声明前紧邻的 Javadoc，解析 `@param` 标签。
   - 对每个 component 要求存在非空 `@param` 描述，并且描述包含至少一个中文 Han 字符。
2. 将 gate 接入：
   - `scripts/quality/run_quality_gate.py` 增加 `javaRecordComponentJavadocs` 命令。
   - `scripts/quality/quality_targets.py` 把该 gate 放入 `java-src` baseline 和 Java source pattern。
   - 根 `build.gradle.kts` 增加 `verifyJavaRecordComponentJavadocs`，并挂到 `check`。
3. Codex Stop 修复：
   - 确认 `.codex/hooks/stop_check.sh` 把 Stop stdin 传给 `agent_stop_check.py`，保留 shared runner 对 dirty/untracked files 的 fail-closed 路由。
   - 增加/调整测试，证明缺少 session id 且存在 untracked Java 文件时，Stop 仍会选中 `java-src`。
4. 修复现有 record 注释：
   - 将英文 record Javadoc 改为中文。
   - 为每个 component 补充 `@param` 中文说明。

## Risks

- 简单源码解析可能误判复杂 record header。通过状态机按括号/尖括号/数组层级拆分，并用测试覆盖注解、泛型、换行和紧凑构造器降低风险。
- 全量扫描可能暴露历史 record 债务。按门禁要求一次性修复当前 Java 源码中的 record Javadoc，避免新 gate 首次运行即失败。
- Codex hook 可用 stdin 字段取决于宿主。Stop wrapper 只做透传，不创造伪 session；缺 identity 时仍以 git dirty/untracked fail-closed 保守触发。

## Rollback

删除新增 checker、Gradle task、quality target 映射和相关测试，并还原 record Javadoc 文案即可回滚；Codex Stop wrapper 如有问题可恢复为原始 `exec python3 ...` 入口。

## Validation

验证分三层：

- 规则级：pytest 覆盖 checker 的 pass/fail 样例。
- 集成级：`run_quality_gate.py --target java-src`/required runner dry-run 或 focused changed-files 能选中并执行新 gate。
- 仓库级：根 Gradle `verifyJavaRecordComponentJavadocs` 与 OpenSpec/harness validators 全部通过。
