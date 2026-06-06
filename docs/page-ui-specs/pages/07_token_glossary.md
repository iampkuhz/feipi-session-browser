# Token Glossary 页面规约

## 定位

Token Glossary 是轻量 reference 页面，解释 token 口径、派生指标、provider 字段映射和 badge 语义。该页只承载帮助理解数据口径的静态说明，不替代业务页面上的常驻指标。

## 页面布局

- 路由：`/glossary`；模板：`glossary.html`。
- Page Head 左侧显示 `Token Glossary` 和一句中文说明。
- 摘要 KPI 区固定为 `Token Types`、`Derived Metrics`、`Provider Fields`、`Round Signals`。
- Filter Card 放在摘要 KPI 下方，只搜索术语页内容。
- 内容区依次为 `Badge Reference`、`Token Types`、`Derived Metrics`、`Provider Field Mapping`、`Round Signals`。
- `Token Types`、`Derived Metrics`、`Provider Field Mapping`、`Round Signals` 均使用通用 `Compact Table` 组件。

## 控件和候选项

- 搜索框搜索术语、指标、provider、字段名。
- Compact Table 排序只作用于当前表格。
- Badge Reference 不提供交互，只作为视觉语义样例。

## 文字内容

- 页面标题固定为 `Token Glossary`。
- 摘要 KPI label 固定为 `Token Types`、`Derived Metrics`、`Provider Fields`、`Round Signals`。
- `Token Types` 表列固定为 `Metric`、`Definition`、`Formula`、`Provider Fields`。
- `Derived Metrics` 表列固定为 `Metric`、`Formula`、`Interpretation`。
- `Provider Field Mapping` 表列固定为 `Provider`、`Model Family`、`Fresh`、`Cache Read`、`Cache Write`、`Output`。
- `Round Signals` 表列固定为 `Signal`、`Definition`、`Used In`。

## 数据指标与口径

### Token Types

- 固定覆盖 `Input Fresh`、`Cache Read`、`Cache Write`、`Output Visible`、`Input-side Total`、`Total Tokens`。
- `Provider Fields` 单元格展示 Anthropic、OpenAI、Codex、Qoder 的字段名摘要。
- 字段不上报时显示 `Not reported` badge。
- 字段由其它字段推导时显示 `Estimated` badge，并说明推导公式。
- 示例行固定包含 `Cache Read`、`Provider cache hit input tokens`、`cache_read_input_tokens`、`Anthropic: cache_read_input_tokens`。

### Derived Metrics

- 固定覆盖 `Cache Read Ratio`、`Cache Write Ratio`、`Output Ratio`、`Tools / Round`、`Tokens / Round`、`Tokens / Minute`、`Failed / Session`。
- 每个公式必须与产品聚合口径一致。
- Interpretation 必须说明该指标在 Dashboard、Sessions、Session Detail 中的使用位置。
- 示例行固定包含 `Cache Read Ratio`、`Cache Read / Input-side Total`、`cache reuse health`。

### Provider Field Mapping

- 固定覆盖 Anthropic、qwen Anthropic compatible、OpenAI、Codex、Qoder。
- 每行必须说明 Fresh、Cache Read、Cache Write、Output 的来源字段。
- provider 未上报字段时使用 `Not reported`，不得留空。
- 示例行固定包含 `Anthropic`、`Claude 4`、`input_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`、`output_tokens`。

### Round Signals

- 固定覆盖 `round`、`step`、`batch`、`tool`、`subagent`、`failure`。
- `Used In` 固定列出使用页面和组件，例如 `Session Detail Trace`、`Dashboard Failure Signals`。
- 示例行固定包含 `failure`、`failed tool result, attribution error`、`Session Detail Trace / Dashboard Failure Signals`。

## 交互逻辑

- 输入搜索词后，只隐藏不匹配的术语项和表格行，不改变页面 URL。
- 清空搜索恢复所有内容。
- 搜索无结果时展示状态条，并保留搜索框。
- 点击表头排序不影响其它表格。

## 状态

- 搜索无结果：展示“没有匹配的术语”和换关键词提示。
- 字段不上报：使用 muted badge，不留空。
- 字段估算：使用估算标识，并说明依据。

## 禁止项

- 不把 Glossary 做成复杂知识库。
- 不使用营销页结构。
- 不在主业务流程中依赖 Glossary 承载必须常驻显示的数据。
- 不把 Glossary 作为核心业务主导航目标。
