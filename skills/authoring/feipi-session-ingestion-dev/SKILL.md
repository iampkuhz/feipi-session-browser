---
name: feipi-session-ingestion-dev
disable-model-invocation: true
description: 用于本仓库 session ingestion / token attribution 专项开发的最小上下文执行规则；纯 UI、纯文档、纯 OpenSpec 编排不要使用。
---

# Session ingestion / token attribution 专项开发

本 skill 为 session ingestion pipeline 和 token attribution 模型开发提供最小上下文执行规则。覆盖格式 parser、规范化数据模型、token 归因和 cost 计算，避免通用 implementer 每次重新理解 ingestion 架构。

## 何时使用

- 新增或修改会话格式 parser（Claude Code / Codex / Qoder）。
- 修改 `NormalizedCall`、`NormalizedSession` 或 `NormalizedMessage` 数据模型。
- 修改 token 归因逻辑或 cost 计算。
- 新增会话来源或 agent 平台支持。
- 修复 ingestion pipeline 中的数据保真度问题。

## 不要何时使用

- 纯 UI 模板修改 → 使用对应的 UI skill。
- 纯文档、纯 OpenSpec 编排 → 使用 `feipi-openspec-orchestrate-change`。
- 纯 Java 模块边界变更 → 使用 `feipi-java-feature-dev`。
- 纯质量门诊断 → 使用 `feipi-quality-gate-diagnosis`。

## 输入最小化

只读取以下必要片段：

1. `core-domain` 中 `NormalizedCall` / `NormalizedSession` / `NormalizedMessage` 的定义。
2. 目标 parser 模块的源码 — 只读与当前变更直接相关的文件。
3. 相邻测试文件 — 只读与当前变更直接相关的测试。
4. `shared/SESSION_SCHEMA.md` — 规范化会话 schema 契约。

不要整个模块扫描。不要预读无关模块的源码。

## 执行步骤

1. 搜索定位目标模块和入口：使用 `rg` 定位目标类名或方法，确定所属 Gradle 模块。
2. 读取 `shared/SESSION_SCHEMA.md` 确认 schema 契约。
3. 读取目标 parser 或数据模型文件，只读必要片段。
4. 查找相邻测试，确认测试覆盖。
5. 修改代码，保持 `NormalizedCall` schema 向后兼容。
6. 新增字段必须有默认值；语义变更通过 `meta` 扩展。
7. `inputTokens`、`outputTokens`、`cacheCreationInputTokens`、`cacheReadInputTokens` 必须对齐上游 API 语义。
8. 运行验证门禁。
9. 输出变更和验证。

## 文件边界

- 数据模型：`java/core-domain/src/main/java/` 下的 `NormalizedCall` / `NormalizedSession` / `NormalizedMessage`。
- Parser：`java/parser-claude-code/`、`java/parser-codex/`、`java/parser-qoder/`。
- 测试代码：对应模块 `src/test/java/`。
- 构建配置：对应模块 `build.gradle.kts`。
- Schema 契约：`shared/SESSION_SCHEMA.md`。

不要跨模块引入类。不要在 parser 层直接操作索引或查询 API。

## 约束

- **必须中文回复**，commit message 用英文前缀（如 `fix(parser): ...`）
- 不修改 `skills/` 下的其他 skill
- 不绕过质量门禁
- 不修改真实 session 数据、缓存、密钥或个人配置
- 不改 `openspec/` 下的 spec 文件（除非本任务明确要求）
- 所有 spec 变更必须走 OpenSpec change
- 不删 required gates，不新增 skip
- `NormalizedCall` schema 变更必须保持向后兼容，或在 `NormalizedCall.meta` 中扩展
- Token 字段必须对齐上游 API 语义

## 验证门禁

以下门禁不是每次都全部运行，但触发时 required gate 不能 skipped：

- `./scripts/session-browser.sh test` — Java 编译和测试。
- `python scripts/checks/check_java_module_boundaries.py` — 模块边界检查。
- `python scripts/checks/check_manifest.py` — manifest 一致性校验。
- `python scripts/gates/cli.py` — 全量 required quality gates。

选择策略：

- 只改 parser 或数据模型 → 至少运行 `test` + `check_java_module_boundaries.py`。
- 改 schema 契约 → 追加 `check_manifest.py`。
- 收口前 → 运行 `python scripts/gates/cli.py`。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 改动的模块列表。
- Token 归因影响（如有）。
- 向后兼容性说明。
- 门禁运行结果。
- 后续风险或 TODO。

## 参考索引

| 文件 | 何时读取 |
|------|----------|
| `references/architecture.md` | 改 parser / attribution 代码前 |
| `references/glossary.md` | 首次接触本 skill 领域时 |
| `references/patterns.md` | 调试 token 不一致或数据丢失时 |
| `templates/handoff.md` | 派发子任务给 implementer 时 |
| `templates/report.md` | 写变更报告时 |
