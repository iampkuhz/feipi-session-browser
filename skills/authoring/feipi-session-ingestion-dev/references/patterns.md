# Session Ingestion — 常见模式与排障指南

> 调试 token 不一致、数据丢失或 parser 问题时阅读。

## 模式 1：新增平台 Parser

### 场景
需要支持新的 agent 平台（如 Cursor、Windsurf 等）。

### 步骤

1. 在 `core-domain` 确认 `NormalizedCall` / `NormalizedSession` 能否承载新平台数据
2. 如需扩展，优先使用 `NormalizedCall.meta` 字段，避免改 schema
3. 创建新 Gradle 模块 `parser-<platform>`，依赖 `core-domain`
4. 实现 `SessionParser` 接口，将原始格式转为 `NormalizedSession`
5. 编写单元测试，覆盖正常数据、边界数据和异常数据
6. 在 `skill-registry.yaml` 和 `agent-runtime.manifest.yaml` 注册

### 注意
- Token 字段缺失时记 `0`，不做估算
- 时间戳统一为 `Instant`（UTC）
- `sessionId` 生成策略：优先用平台原始 ID，缺失时用 content hash

---

## 模式 2：Token 数量不一致

### 场景
用户报告总 token 数与平台 UI 显示不一致。

### 排查步骤

1. **确认数据源**：检查原始 JSONL/JSON 中 `usage` 字段是否存在
2. **确认 parser 提取逻辑**：是否遗漏了 `cacheCreationInputTokens` 或 `cacheReadInputTokens`
3. **确认归因规则**：`inputTokens` 是否重复计入了缓存部分
4. **确认 cost 计算**：pricing table 是否为当前最新价格

### 常见原因
- 上游 API 返回的 token 数是近似值（四舍五入）
- 缓存 token 和 inputToken 的语义在不同 API 版本间有变化
- 多模态内容（图片）的 token 计算方式不同

---

## 模式 3：数据丢失

### 场景
某些 session 或 call 在索引后查不到。

### 排查步骤

1. **检查 parser 是否跳过**：日志中是否有 `skipped` 或 `unsupported format` 记录
2. **检查 Normalizer 是否丢弃**：是否有字段校验失败导致整个 call 被丢弃
3. **检查索引写入**：SQLite WAL 模式下是否有未 flush 的数据
4. **检查查询条件**：session ID 大小写、时间范围是否正确

### 常见原因
- 原始文件格式不标准（截断的 JSONL、损坏的 JSON）
- 时间戳格式不统一（秒 vs 毫秒 vs 微秒）
- 编码问题（非 UTF-8 内容）

---

## 模式 4：Schema 向后兼容扩展

### 场景
需要给 `NormalizedCall` 添加新字段。

### 决策树

```
新字段是否所有平台都能提供？
├── 是 → 直接加到 NormalizedCall，给默认值
└── 否 → 放入 NormalizedCall.meta
         └── 是否有 2+ 个消费者需要？
             ├── 是 → 考虑升级为正式字段（给默认值）
             └── 否 → 保持在 meta 中
```

### 注意
- 新字段必须有默认值（`0`、`""`、`null` 等）
- 已有字段语义变更不能直接改，必须通过 `meta` 扩展
- 删除字段必须先 `@Deprecated`，至少保留一个版本

---

## 模式 5：多轮对话中的 Token 归因

### 场景
一个 session 中有多次 API 调用，需要正确归因每次调用的 token。

### 原则
- 每次 API 调用独立记录 token，不合并
- 系统提示的 token 归因到第一次调用
- 工具调用结果如果触发新的 API 调用，token 归因到新调用
- 重试的调用只计最后一次成功的 token

### 注意
- 某些平台会把多次 API 调用合并为一条记录，parser 需要拆分
- 缓存 token 只在第一次调用时产生 cacheCreation，后续调用产生 cacheRead
