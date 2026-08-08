---
name: feipi-java-feature-dev
disable-model-invocation: true
description: 用于本仓库 Java/Gradle/API/CLI 功能研发的最小上下文执行规则；纯 UI、纯文档、纯 OpenSpec 编排不要使用。
---

# Java 功能研发

本 skill 为仓库 Java/Gradle 功能研发提供最小上下文执行规则。覆盖模块边界、分层约束、质量门和 Java 规约，避免通用 implementer 每次重新理解模块结构。

## 何时使用

- 新增或修改 Java 产品代码（core-domain、sources、index-sqlite、application、web 等模块）。
- 新增或修改 Gradle 构建配置、API snapshot、CLI 入口。
- 涉及 DTO/Mapper/DAO/Repo/Service 分层变更。
- 需要理解模块依赖方向和 forbidden import 规则的功能开发。

## 不要何时使用

- 纯 UI 模板修改（Thymeleaf、CSS）→ 使用 `feipi-session-detail-ui-dev`。
- 纯文档、纯 OpenSpec 编排 → 使用 `feipi-openspec-orchestrate-change`。
- 纯 session ingestion 逻辑 → 使用 `feipi-session-ingestion-dev`。
- 纯质量门诊断 → 使用 `feipi-quality-gate-diagnosis`。
- 不涉及 Java 源码的配置或脚本修改。

## 输入最小化

只读取以下必要片段：

1. `settings.gradle.kts` — 只需 include 块。
2. 目标模块的 `build.gradle.kts` — 只需 dependencies 块。
3. `config/architecture/java-modules.yaml` — 只需目标模块的条目和 forbiddenImports。
4. 相邻测试文件 — 只读与当前变更直接相关的测试。

不要整模块扫描。不要预读无关模块的 build 文件或源码。

## 执行步骤

1. 搜索定位模块和入口：使用 `rg` 定位目标类名或方法，确定所属 Gradle 模块。
2. 读取 `settings.gradle.kts` 和相关模块 build 文件，只读必要片段（include 块和 dependencies 块）。
3. 查找并读取 `src/test/` 下与改动直接相关的相邻测试或 fixture。
4. 先改测试或 fixture，再改实现；如果当前仓库模式不是 TDD，可以改完立即补测试。
5. 不跨层访问：API/CLI 不直接读底层存储，Service 不写 UI 模板，Repo 不做渲染。
6. DTO/Mapping/DAO/Repo/Service 命名按现有模块模式，不新发明一套分层。
7. Lombok、枚举、`@SuppressWarnings` 等 Java 规约只在涉及 Java 源码时加载相关 OpenSpec。
8. 运行 Java target gate。
9. 输出变更和验证。

## 文件边界

- 生产代码：`java/<module>/src/main/java/` 下对应模块的包路径。
- 测试代码：`java/<module>/src/test/java/` 下对应模块的包路径。
- 构建配置：`java/<module>/build.gradle.kts`，`gradle/build-logic/`。
- 模块边界配置：`config/architecture/java-modules.yaml`。
- 脚本入口：`scripts/session-browser.sh`。

不要跨模块引入类。不要在 API/CLI 层直接操作底层存储。

## 验证门禁

以下门禁不是每次都全部运行；被选中的 Gate 必须完整执行并给出明确结论：

- `./scripts/session-browser.sh test` — Java 编译和测试。
- `./gradlew check` — 模块边界、package 归属、forbidden import。
- `python3 scripts/gates/cli.py --mode incremental` — 根据当前改动自动选择并运行相关 Gate。

选择策略：

- 只改 Java 源码 → 至少运行 `test` + `Gradle check`。
- 改构建配置或模块依赖 → 必须运行 `./gradlew check`。
- 普通提交或交接收口前 → 运行 `python3 scripts/gates/cli.py --mode incremental`。
- 发布、周期审计或大迁移 → 运行 `python3 scripts/gates/cli.py --mode full`。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 改动的 Java 模块列表。
- 模块依赖方向变化（如有）。
- 门禁运行结果。
- 后续风险或 TODO。
