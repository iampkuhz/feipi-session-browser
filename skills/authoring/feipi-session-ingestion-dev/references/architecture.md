# Ingestion Pipeline 架构

> Session ingestion / token attribution 模块的架构参考。
> 改 parser 或 attribution 代码前必读。

## 整体流程

```
原始会话文件 (JSONL / JSON)
    │
    ▼
┌─────────────────────┐
│  Format Parser       │  ← 平台特定：claude-code / codex / qoder
│  (parser-*)          │
└─────────┬───────────┘
          │ 原始 Call / Message
          ▼
┌─────────────────────┐
│  Normalizer          │  ← 统一为 NormalizedCall / NormalizedMessage
│  (core-domain)       │
└─────────┬───────────┘
          │ NormalizedSession
          ▼
┌─────────────────────┐
│  Token Attribution   │  ← inputTokens / outputTokens / cache* 归因
│  (core-domain)       │
└─────────┬───────────┘
          │ 带 cost 的完整 session
          ▼
┌─────────────────────┐
│  Index / Query       │  ← SQLite 索引、API 查询
│  (index-sqlite, api) │
└─────────────────────┘
```

## 核心数据模型

### NormalizedCall

一次 LLM 调用的规范化表示。关键字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `String` | 调用唯一标识 |
| `sessionId` | `String` | 所属会话 |
| `model` | `String` | 模型名称 |
| `inputTokens` | `Int` | 输入 token 数 |
| `outputTokens` | `Int` | 输出 token 数 |
| `cacheCreationInputTokens` | `Int` | 缓存创建 token 数 |
| `cacheReadInputTokens` | `Int` | 缓存读取 token 数 |
| `timestamp` | `Instant` | 调用时间 |
| `meta` | `Map<String, Any>` | 扩展元数据（向后兼容扩展点） |

### NormalizedSession

一次完整会话的规范化表示，包含多个 `NormalizedCall` 和 `NormalizedMessage`。

### NormalizedMessage

会话中的一条消息（用户输入或助手回复）。

## Token Attribution 规则

1. **直接从 API response 提取**：优先使用上游返回的 `usage` 字段
2. **缓存 token 独立计算**：`cacheCreationInputTokens` 和 `cacheReadInputTokens` 分别记录，不混入 `inputTokens`
3. **缺失值处理**：如果上游未返回某字段，记为 `0`，不做估算
4. **Cost 计算**：基于 model pricing table，公式为：
   ```
   cost = inputTokens * inputPrice
        + outputTokens * outputPrice
        + cacheCreationInputTokens * cacheCreationPrice
        + cacheReadInputTokens * cacheReadPrice
   ```

## 模块边界

| 模块 | 职责 | 本 skill 关注点 |
|------|------|----------------|
| `core-domain` | NormalizedCall / Session / Message 数据模型 | 数据模型变更 |
| `parser-claude-code` | Claude Code JSONL 解析 | parser 变更 |
| `parser-codex` | Codex JSON 解析 | parser 变更 |
| `parser-qoder` | Qoder 格式解析 | parser 变更 |
| `index-sqlite` | SQLite 索引构建 | 仅当 schema 变更影响索引时 |
| `api` | 查询 API | 仅当数据模型变更影响 API 时 |

## 向后兼容原则

- `NormalizedCall` 新增字段必须给默认值
- 已有字段语义变更必须通过 `meta` 扩展
- 删除字段必须先标记 `@Deprecated` 至少一个版本
- Parser 输出格式变更必须有 migration 或 fallback
