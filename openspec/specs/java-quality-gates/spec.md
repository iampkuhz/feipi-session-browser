# Java 质量门模块规约

## 模块定位

`java/tests/quality-gates` 是 Java 化质量门模块，Gradle path 为 `:java:tests:quality-gates`。

质量门不是产品运行时模块，不进入生产 classpath。它同时包含：

- main code：gate 框架、规则实现和 CLI 入口，供 `JavaExec` 调用。
- test code：JUnit 测试和 fixtures，保护规则本身。

## 迁移策略

每个 Python gate 迁移到 Java 遵循固定协议：

1. deterministic corpus：冻结旧 Python 的 violation key 或输出快照。
2. fixtures：建立覆盖有效和无效输入的 Java 源码 fixture corpus。
3. Java implementation：在 quality-gates 模块实现对应 `QualityGate`。
4. parity diff：在迁移提交内用旧 Python 和新 Java 对同一 corpus 做一次性对比。
5. root check 切换：root `build.gradle.kts` 中的 Gradle task 从 Python Exec 切换到 Java gate。
6. 删除旧 Python、parity runner、adapter 和重复测试；不得保留 migration-only 双栈。

## Batch 1 范围

Batch 1 只迁移 record component Javadoc gate：

```text
the retired Python record-component Javadoc gate
```

迁移后的 Java gate id：

```text
record-component-javadocs
```

### 违规规则

Java 实现必须保持旧 Python 的三类违规：

- `RECORD_JAVADOC_MISSING`：record 声明前没有属于该 record 的类型 Javadoc。
- `RECORD_COMPONENT_PARAM_MISSING`：record component 在类型 Javadoc 中缺少同名 `@param`。
- `RECORD_COMPONENT_PARAM_NOT_CHINESE`：record component 的 `@param` 描述不包含中文汉字。

中文检测正则：

```text
[㐀-䶿一-鿿豈-﫿]
```

## Batch 2 唯一 owner

Java registry 当前负责：

- `record-component-javadocs`：record 类型与 component 中文 `@param`。
- `no-pmd-suppressions`：禁止未审批的 `@SuppressWarnings("PMD.*")`。
- `java-api-snapshot`：使用 compiler API 生成并比对 public API baseline。

以下内容仍不属于 Java registry：

- 新增 `@Example` 注解和 record component examples 强制规则。
- record component layout 强制规则。
- 修正 `@Ratio` 语义。
- 全量 record metadata 更新。
- 迁移 `check_code_comment_language.py`。
- 迁移 `run_required_quality_gates.py`。

## 未来预留

以下 gate id 可在 registry 中预留但不得启用：

- `record-component-examples`
- `record-component-layout`
- `chinese-java-comments`
- `no-skipped-tests`

预留 id 如果被调用，应返回清晰错误 `gate not implemented`，不得 silently pass。

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

root `check` 直接 dependsOn 该 task，不再注册逐 Gate alias。跨语言 comment policy 继续由 catalog
中的 Python owner 执行；Java test skipped/aborted 由 Gradle `verifyNoSkippedJavaTests` 唯一检查。
