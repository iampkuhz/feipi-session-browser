# Token Glossary 页面规约

## 定位

Token Glossary 是轻量 reference 页面，解释 token 口径、派生指标、provider 字段映射和 badge 语义。

## 页面布局

- 路由：`/glossary`；模板：`glossary.html`。
- Page Head 左侧显示 `Token Glossary` 和一句中文说明。
- 摘要 KPI 区固定为 Token Types、Derived Metrics、Provider Fields、Round Signals。
- Filter Card 放在摘要 KPI 下方，只搜索术语页内容。
- 内容区依次为 Badge Reference、Token 概览、Token 组成表、派生指标表、Provider 映射表。

## 控件和候选项

- 搜索框支持术语、指标、provider、字段名。
- 表格排序只作用于当前表格。
- Badge Reference 不提供交互，只作为视觉语义样例。

## 文字内容

- 页面标题固定为 `Token Glossary`。
- 摘要 KPI label 固定为 Token Types、Derived Metrics、Provider Fields、Round Signals。
- Token 组成表列固定为 指标、定义、公式、Anthropic、OpenAI。
- 派生指标表列固定为 指标、公式、解读。
- Provider 映射表列固定为 Provider、模型、Input Fresh、Cache Read、Cache Write、Output。

## 数据指标与口径

- Token Types 至少覆盖 Input Fresh、Cache Read、Cache Write、Output Visible、Input-side Total、Total Tokens。
- Derived Metrics 至少覆盖 Cache Reuse、Cache Write Ratio、Output Ratio、Tools/Round、Tokens/Round、Tokens/Minute、Failed/Session。
- Provider Fields 至少覆盖 Anthropic、qwen Anthropic 兼容、OpenAI、Codex。
- Round Signals 至少覆盖 round、step、batch、tool、subagent、failure。
- 公式必须与产品聚合口径一致；不确定字段必须标注估算或不上报。

## 交互逻辑

- 输入搜索词后，只隐藏不匹配的术语项或表格行，不改变页面 URL。
- 清空搜索恢复所有内容。
- 搜索无结果时展示状态条，并保留搜索框。
- 点击表头排序不影响其它表格。

## 状态

- 搜索无结果：展示“没有匹配的术语”和换关键词提示。
- 字段不上报：使用 muted badge，不留空。
- 字段估算：使用估算标识，并说明依据。

## 禁止项

- 不把 Glossary 做成复杂知识库或营销页。
- 不在主业务流程中依赖 Glossary 承载必须常驻显示的数据。
- 不把 Glossary 作为核心业务主导航目标。
