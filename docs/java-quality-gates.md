# Java Quality Gate 维护说明

Java 专属 source rule 的唯一公开入口是
`:java:tests:quality-gates:runJavaQualityGates`。Gate catalog 可声明多个 `java_rules`，executor
将同一 plan 的 rule id 聚合到一个 Gradle command；CLI 在一个 JVM 中只解析一次候选源码。

## 唯一 owner 盘点

| rule_id | purpose | single owner | catalog / callers | trigger / changed-files | process | baseline duration | decision |
|---|---|---|---|---|---|---|---|
| `record-component-javadocs` | record component 中文 `@param` | Java compiler rule | `recordComponentJavadocs` / root `check` | `java/**/src/main/java/**/*.java`; environment | shared JavaExec | Gradle cold 29.39s, warm 1.26s | 保留 Java owner，删除 parity/parser 与 Architecture 重复 owner |
| `no-pmd-suppressions` | 禁止压制自定义 PMD rule | Java compiler rule | `noJavaSuppressWarnings` / root `check` | main Java; environment | shared JavaExec | legacy Python cold 1.17s, warm median 0.55s | 迁移并删除 Python owner |
| `java-api-snapshot` | public API baseline | Java compiler rule | `javaApiSnapshot`; full only | main Java / snapshot; full | shared JavaExec | legacy Python cold 8.11s, warm median 1.29s | 迁移并删除 Python owner；只有显式 write mode 可更新 baseline |
| `noJavaTestSkips` | JUnit XML 失败/空集/跳过/中止 fail-closed | root Gradle `verifyNoSkippedJavaTests` | `noJavaTestSkips`, root `check` | Java tests/build; none | existing Gradle group | legacy Python cold 0.76s, warm median 0.29s | 删除 Python 重读 XML，复用 Gradle owner |
| module boundary | Gradle module/package/import 边界 | `java:tests:architecture` / root `check` | `javaCheck` | Java/build | existing Gradle group | stub only | 删除 `javaModuleBoundaries` alias 和 Python module stub |
| source comment language | Java/Kotlin/KTS/script 注释语言 | `source.comment-language` Python checker | `javaChineseComments` | 跨语言 source | Python | 不属于迁移集 | 保留 Python；删除 root Java-only 重复 wrapper |
| enum external value | enum 对外值 | Java architecture owner | no legacy caller | Java | existing Gradle group | n/a | baseline 已无 Python checker，不恢复 |

## 执行契约

- rule 不运行 Git，只消费 CLI 已解析的 repository-relative 候选。
- `QUALITY_CHANGED_FILES` 为 JSON string array；非法输入 fail-closed。空候选输出
  `NOT_APPLICABLE`，不伪装成 skipped。
- JSON summary 固定包含 `status`、`candidateCount`、`rules` 和 `violations`；violation 稳定字段为
  `rule/path/line/code/message/attributes`。
- 默认执行 `record-component-javadocs,no-pmd-suppressions`；`java-api-snapshot` 由 full plan
  声明式加入。
- API baseline 维护只允许：
  `./gradlew :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=java-api-snapshot -PfeipiJavaApiSnapshotWrite=true`。

## 删除证据

| deleted_logic | old_location | remaining_single_owner | deleted_LOC | behavior_evidence | why_not_file_merge |
|---|---|---|---:|---|---|
| Java API text parser/checker | `scripts/checks/check_java_api_snapshot.py` | `JavaApiSnapshotRule` | 643 | legacy/current body 逐行 parity；新 rule 全仓 PASS | 合并会保留 Python/Java 双栈 |
| PMD suppression scanner | `scripts/checks/check_no_java_suppress_warnings.py` | `NoPmdSuppressionsRule` | 84 | exact exception 和 violation corpus PASS | compiler AST 已是唯一正确 owner |
| JUnit XML checker | `scripts/checks/check_no_java_test_skips.py` | root Gradle `verifyNoSkippedJavaTests` | 154 | root task 保留 missing/empty/fail/error/skip/abort contract | 合并会重复读取同一 XML |
| module stub / logical alias | Python stub + catalog `javaModuleBoundaries` | Architecture/root `check` | 3 + catalog block | planner/catalog tests PASS | alias 没有独立行为 |
| parity/discovery/manual parser/reporter | `ParityRunner`, discovery, `JavaRecordSourceParser`, old DTO/reporter | registry + `JavaSourceSet` + `QualitySummary` | 1,435 | 8-rule/CLI tests；337 candidates；3 rules/0 violations | 文件合并不会消除重复职责 |
| record component Architecture branch | `ChineseJavadocVerifier` | `RecordComponentJavadocsRule` | 72 net | 17 Architecture fixtures PASS，非 record Javadoc 行为保留 | 必须删除第二 owner |
| Python-only / implementation-detail tests | API/module direct tests and old Java parser/discovery tests | Java rule/CLI + planner corpus | 623+ | path/line/code、nested/generic/annotation、Windows、N/A 保留 | 永久双 corpus 会恢复 parity 模式 |

## 量化结果

LOC 按迁移范围 authored production/test 计数，不包含 generated snapshot、YAML catalog 与本文档：

- production：`3901 -> 2538`（Python checker + quality-gates main + Architecture gate implementation）。
- test / fixture：`1263 -> 719`。
- combined：`5164 -> 3257`，减少 `36.9%`。
- Java 专属 Python checker：`4 -> 0`；对应 Python direct test：`208 -> 80` LOC。
- 文件：删除 21，新增 9；其中 8 个是唯一 Java framework/rule/test，另 1 个为本维护文档。
- Java 专属检查进程：Gradle + 3 Python `4 -> 1`；三个 Java source rules 共用一个 JavaExec JVM。
- 聚合进程计时：cold `39.43s -> 30.95s`；warm `3.39s -> 1.27s`（降低 `62.5%`）。
  baseline 为旧 Gradle 记录加三个 legacy Python 进程；post 为配置缓存已复用的唯一 Gradle group。

## Root build hunk 审计

`build.gradle.kts` 只删除 Java API/comment/record 重复 task、helper 和直接失效依赖，并将
root `check` 接到唯一 `runJavaQualityGates`。从
`// Reuse quality gates —— PMD only.` 开始的禁止区域与 baseline 字节一致，SHA-256 均为
`96d8103ffcc35f6282c40945156bac0b6e492962f9d27e01003d5fecd643163c`。

## 直接引用闭包

- `openspec/specs/agent-harness/spec.md`：用唯一 task 替换已删除 record alias。
- `tests/checks/test_shared_cli.py`：删除已删 Python registry id 断言。
- `tests/quality/test_java_module_boundaries_gate.py`：删除 logical alias 契约，保留 CPD/reuse 断言不变。
