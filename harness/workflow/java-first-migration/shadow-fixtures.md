# Golden Fixture 与 Shadow Comparator

本文档描述 golden fixture 格式、shadow comparator 使用方式和差异分类规则。
该机制为 Java-first 切流提供 scan/parse/normalize 管线的验收基础。

## 1. Golden Fixtures

### 1.1 存放位置

```
java/contract-tests/src/test/resources/golden-fixtures/
├── claude-code/
│   └── minimal-session.jsonl
├── codex/
│   └── minimal-session.jsonl
└── qoder/
    └── minimal-session.jsonl
```

### 1.2 格式规范

每个 fixture 文件为 JSONL 格式（每行一个 JSON 对象），内容要求：

- **合成数据**：所有 fixture 均为人工构造的最小脱敏样本，不包含真实 session 数据。
- **自包含**：每个文件至少包含 user/assistant/tool_result 事件，覆盖基本归一化路径。
- **确定性**：同一文件多次读取产生相同的 JSON 事件序列。

各 agent 的 fixture 字段遵循以下提取规则（对应 `JsonSourceRecordMapper`）：

| 字段 | 提取方式 | 说明 |
|------|----------|------|
| `type` | 直接读取 | 事件类型（assistant, user, tool_result） |
| `id` / `uuid` | 优先 `id`，回退 `uuid` | 调用标识 |
| `model` | 直接读取 | 模型名称 |
| `timestamp` | 直接读取 | 时间戳文本 |
| `turn_id` / `turnId` | 优先 `turn_id`，回退 `turnId` | 轮次标识 |
| `usage` | 嵌套对象 | 包含 `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` |
| `content` / `parts` | 数组 | 工具调用声明列表，每项需有 `type: "tool_use"`, `id`, `name` |
| `tool_use_id` | 直接读取 | 工具结果引用的调用 ID |
| `name` | 直接读取 | 工具名称 |

### 1.3 扩展 fixture

新增 fixture 时应遵循：

1. 使用 `synthetic` 或 `syn` 前缀命名 ID，避免与真实数据混淆。
2. 每个文件不超过 20 行事件，保持最小可验证性。
3. 如需测试特定场景（如子 agent、多轮对话），在对应 agent 目录下添加新文件。

## 2. Shadow Comparator

### 2.1 工具类

`ShadowComparator` 位于 `contracttest/shadow/ShadowComparator.java`。

```java
ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);
```

参数说明：
- `baseline`：参考实现产生的 `NormalizedSessionArtifact`（如 Python 参考输出或 golden 期望值）。
- `candidate`：Java 管线产生的 `NormalizedSessionArtifact`。

### 2.2 对比策略

对比按优先级从高到低执行：

1. **前置检查**：null 检查、agent 一致性。不一致则 `INCOMPARABLE`。
2. **Schema 版本**：不一致则 `BREAKING_DIFFERENCE`。
3. **结构数量**：调用数量、工具执行数量。不一致则 `BREAKING_DIFFERENCE`。
4. **逐调用对比**：
   - `callId` 不一致 → `BREAKING_DIFFERENCE`
   - `callIndex` 不一致 → `BREAKING_DIFFERENCE`
   - `token 总量` 不一致 → `BREAKING_DIFFERENCE`
   - 工具引用数量不一致 → `BREAKING_DIFFERENCE`
   - `model` 差异 → `COMPATIBLE_DIFFERENCE`
5. **逐工具执行对比**：
   - `toolCallId` 不一致 → `BREAKING_DIFFERENCE`
   - `declaredByCallId` 不一致 → `BREAKING_DIFFERENCE`
   - `name` 差异 → `COMPATIBLE_DIFFERENCE`
6. **Session 元数据**：
   - `totalTokens`、`declaredTools`、`executedTools` 不一致 → `BREAKING_DIFFERENCE`
   - `eventCount`、`consumedResults` 差异 → `COMPATIBLE_DIFFERENCE`
7. **诊断信息**：数量差异 → `COMPATIBLE_DIFFERENCE`
8. **源文件**：数量差异 → `COMPATIBLE_DIFFERENCE`

### 2.3 结果判定

```java
result.isCutoverSafe();  // true 表示可切流
```

- `EXACT_MATCH` → 可切流
- `COMPATIBLE_DIFFERENCE` → 可切流（需记录差异清单）
- `BREAKING_DIFFERENCE` → 阻塞切流，需人工审查
- `INCOMPARABLE` → 阻塞切流，需排查原因

## 3. 差异分类规则

| 分类 | 值 | 含义 | 切流影响 |
|------|------|------|----------|
| `EXACT_MATCH` | `exact_match` | 深度一致 | 通过 |
| `COMPATIBLE_DIFFERENCE` | `compatible_difference` | 不影响下游消费 | 通过 |
| `BREAKING_DIFFERENCE` | `breaking_difference` | 可能导致行为变化 | 阻塞 |
| `INCOMPARABLE` | `incomparable` | 无法完成对比 | 阻塞 |

### 3.1 兼容差异示例

- 时间戳格式从 ISO-8601 变为 Unix 毫秒（下游已兼容两种格式）
- Map 键的迭代顺序不同（语义等价）
- 空列表 `[]` 与 null 的差异（下游均视为无数据）
- 诊断信息数量差异（不影响主路径查询结果）

### 3.2 破坏性差异示例

- 调用数量变化（会话结构改变）
- Token 总量变化（计费相关）
- 工具执行关联断裂（调用-工具映射错误）
- Schema 版本变化（持久化格式不兼容）

## 4. 测试链路

```
JSONL fixture
    → [JsonlReader] → List<JsonNode> events
    → [JsonSourceRecordMapper] → List<SourceRecord>
    → [NormalizationEngine] → NormalizedSessionArtifact
    → [ShadowComparator] → ShadowComparisonResult
```

`ShadowFixtureTest` 中每个 agent 至少包含两个测试：

1. `scanNormalizeProducesValidArtifact`：验证链路端到端可用。
2. `determinismViaShadowCompare`：验证两次独立运行结果 `EXACT_MATCH`。
