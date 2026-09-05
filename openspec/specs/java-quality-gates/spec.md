# Java 质量门模块规约

## 模块定位

`java/tests/quality-gates` 是 Java 化质量门模块，Gradle path 为 `:java:tests:quality-gates`。

质量门不是产品运行时模块，不进入生产 classpath。它同时包含：

- main code：gate 框架、规则实现和 CLI 入口，供 `JavaExec` 调用。
- test code：JUnit 测试和 fixtures，保护规则本身。

## Requirements

### Requirement: Gradle 工程根与仓库根分离

Gradle settings、根 build、properties 和 wrapper SHALL 位于 `java/`；从仓库根调用 SHALL 使用 `./java/gradlew -p java`。原 `:java:*` project ID MUST 保留并显式映射 projectDir；中间父项目 SHALL 使用独立聚合目录，不重复加载根脚本。构建 MUST 区分 `buildRoot` 与 `repoRoot`，按资源职责定位配置、测试、脚本与缓存。

#### Scenario: 从两个根目录启动同一构建

- **Given** 顶层不再保留 Gradle 入口或转发文件
- **When** 从仓库根指定 `-p java` 或在 `java/` 内执行 wrapper
- **Then** 项目 ID、任务语义、依赖锁与质量阈值 SHALL 一致
- **And** Checkstyle SHALL 同时设置新 configFile 与 configDirectory，使 suppressions 实际生效

## Record component Javadoc owner

Java gate id：

```text
record-component-javadocs
```

### 违规规则

Java 实现报告以下三类违规：

- `RECORD_JAVADOC_MISSING`：record 声明前没有属于该 record 的类型 Javadoc。
- `RECORD_COMPONENT_PARAM_MISSING`：record component 在类型 Javadoc 中缺少同名 `@param`。
- `RECORD_COMPONENT_PARAM_NOT_CHINESE`：record component 的 `@param` 描述不包含中文汉字。

中文检测正则：

```text
[㐀-䶿一-鿿豈-﫿]
```

## Java registry owners

Java registry 当前负责：

- `record-component-javadocs`：record 类型与 component 中文 `@param`。
- `no-pmd-suppressions`：禁止未审批的 `@SuppressWarnings("PMD.*")`。
- `java-comment-language`：Java 生产源码注释使用中文，并复用 `scripts/gates/config/technical-terms.json`。

以下内容不属于 Java registry：

- 新增 `@Example` 注解和 record component examples 强制规则。
- record component layout 强制规则。
- 修正 `@Ratio` 语义。
- 全量 record metadata 更新。

## 框架结构

```text
com.feipi.session.browser.quality.gates
  cli        — CLI 入口和退出码
  core       — QualityGate 接口、QualityViolation、Context、Registry
  javaapi    — 单次 compiler API source set
  rules      — 具体 gate 规则实现
```

## Gradle 接线

唯一公开 task 为 `:java:tests:quality-gates:runJavaQualityGates`。Gate planner 通过声明式
`java_rules` 聚合 rule id，并在一次 Gradle invocation 中只传一个 `-PfeipiJavaQualityRules`。

root `check` 直接 dependsOn 该 task。默认规则为 `java-comment-language`、
`record-component-javadocs`、`no-pmd-suppressions`；Java test skipped/aborted 由 Gradle
`verifyNoSkippedJavaTests` 唯一检查。`javaBuildVerification` 执行无 task 排除的 root `check`，包含 Checkstyle、Javadoc、
PMD、测试和 Java quality registry；不得使用 `-x`、suppression 或降低规则来回避存量源码问题。
CPD 继续由独立 `reuseStandardCpd` task 拥有，不隐藏进 root `check`。

## 稳定态性能基线

SQLite 详情查找的 `50ms` 本地稳定态预算使用三次预热和七次固定采样的中位数判断。
样本以纳秒比较，不取最快值，不使用失败后重试，也不放宽预算。七次中至少四次达到或超过
`50ms` 时中位数仍应判定失败，查询结果的正确性在计时之外独立断言。
