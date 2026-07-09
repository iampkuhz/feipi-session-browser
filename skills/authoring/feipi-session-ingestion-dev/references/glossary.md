# Session Ingestion / Token Attribution — 领域术语表

首次接触本 skill 领域时阅读。

## 核心概念

| Term | Definition |
|------|-----------|
| **Session** | 一次完整的 agent 交互会话，包含多轮调用和消息。每个 session 有唯一 `sessionId`。 |
| **Call** | 一次 LLM API 调用。一个 session 包含多个 call。每个 call 有独立的 token 用量。 |
| **Message** | 会话中的一条消息，分为 user message 和 assistant message。 |
| **NormalizedCall** | 跨平台统一的调用表示。屏蔽各平台原始格式差异。 |
| **NormalizedSession** | 跨平台统一的会话表示。包含有序 NormalizedCall 和 NormalizedMessage 列表。 |
| **NormalizedMessage** | 跨平台统一的消息表示。包含 role、content、timestamp。 |

## Token 类型

| Term | Definition |
|------|-----------|
| **inputTokens** | 发送给模型的输入 token 数。不含缓存部分。 |
| **outputTokens** | 模型生成的输出 token 数。 |
| **cacheCreationInputTokens** | 用于创建 prompt cache 的输入 token 数。仅 Anthropic API 使用。 |
| **cacheReadInputTokens** | 命中 prompt cache 的输入 token 数。这部分不重复计入 inputTokens。 |
| **Token Attribution** | 将 token 用量归因到具体的 call 和 session 的过程。 |
| **Cost Computation** | 基于 model pricing table 和 token 用量计算费用。 |

## 平台术语

| Term | Definition |
|------|-----------|
| **Claude Code** | Anthropic 的 CLI agent，会话存储为 JSONL 格式。 |
| **Codex** | OpenAI 的 agent，会话存储为 JSON 格式。 |
| **Qoder** | 第三方 agent 平台，有自定义会话格式。 |
| **Format Parser** | 平台特定的会话文件解析器。每个平台一个 parser 模块。 |

## 架构术语

| Term | Definition |
|------|-----------|
| **Ingestion Pipeline** | 从原始会话文件到规范化数据的处理流水线。 |
| **Normalizer** | 将平台特定数据转换为 Normalized* 模型的组件。 |
| **meta** | `NormalizedCall` 的扩展字段。用于向后兼容地添加新属性。 |
| **Backward Compatibility** | 数据模型变更不破坏已有消费方的能力。 |
| **Migration** | 数据模型版本升级时的转换逻辑。 |

## 质量术语

| Term | Definition |
|------|-----------|
| **shared_skills gate** | 所有 agent 共享的技能层。本 skill 通过此 gate 暴露给 agent。 |
| **quality_gates** | 变更必须通过的检查列表。本 skill 要求 `gradle test` 和 `check_manifest.py`。 |
| **OpenSpec change** | 规格变更流程。所有 spec 变更必须走 OpenSpec。 |
