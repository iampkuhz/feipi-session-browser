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
5. API snapshot 文件 — 只在涉及 API 变更时读取。

不要整模块扫描。不要预读无关模块的 build 文件或源码。

## 执行步骤

1. 搜索定位模块和入口：使用 `rg` 定位目标类名或方法，确定所属 Gradle 模块。
2. 读取 `settings.gradle.kts` 和相关模块 build 文件，只读必要片段（include 块和 dependencies 块）。
3. 查找相邻测试和 API snapshot：在 `src/test/` 下查找对应测试，在 `config/api-snapshots/` 下查找 API snapshot。
4. 先改测试或 fixture，再改实现；如果当前仓库模式不是 TDD，可以改完立即补测试。
5. 不跨层访问：API/CLI 不直接读底层存储，Service 不写 UI 模板，Repo 不做渲染。
6. DTO/Mapping/DAO/Repo/Service 命名按现有模块模式，不新发明一套分层。
7. Lombok、枚举、`@SuppressWarnings` 等 Java 规约只在涉及 Java 源码时加载相关 OpenSpec。
8. 运行 Java target gate。
9. 输出变更和验证。

## 文件边界

- 生产代码：`java/<module>/src/main/java/` 下对应模块的包路径。
- 测试代码：`java/<module>/src/test/java/` 下对应模块的包路径。
- 构建配置：`java/<module>/build.gradle.kts`，`build-logic/`。
- API snapshot：`config/api-snapshots/`。
- 模块边界配置：`config/architecture/java-modules.yaml`。
- 脚本入口：`scripts/session-browser.sh`。

不要跨模块引入类。不要在 API/CLI 层直接操作底层存储。

## 验证门禁

以下门禁不是每次都全部运行，但触发时 required gate 不能 skipped：

- `./scripts/session-browser.sh test` — Java 编译和测试。
- `python scripts/quality/check_java_module_boundaries.py` — 模块边界、package 归属、forbidden import。
- `python scripts/quality/check_java_api_snapshot.py` — API snapshot 一致性。
- `python scripts/quality/run_required_quality_gates.py` — 全量 required quality gates。

选择策略：

- 只改 Java 源码 → 至少运行 `test` + `check_java_module_boundaries.py`。
- 改 API 签名 → 追加 `check_java_api_snapshot.py`。
- 改构建配置或模块依赖 → 追加 `check_java_module_boundaries.py --fail-transition`。
- 收口前 → 运行 `run_required_quality_gates.py`。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 改动的 Java 模块列表。
- 模块依赖方向变化（如有）。
- 门禁运行结果。
- 后续风险或 TODO。
