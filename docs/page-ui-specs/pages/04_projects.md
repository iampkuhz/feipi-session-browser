# Projects 页面规约

## 定位

Projects 是项目级入口页，展示已索引工作区的统计、健康信号和进入 Project Detail 的路径。

## 页面布局

- 路由：`/projects`；模板：`projects.html`。
- Page Head 左侧显示 `Projects` 和一句工作区说明。
- Page Head stat pill 显示 project 总数。
- KPI 区固定展示 Projects、Sessions、Total Tokens、Failed Tools。
- Filter Card 放在 KPI 区下方，All Projects 表格上方。
- All Projects 表格占页面主宽度，支持横向滚动。

## 控件和候选项

- 搜索框只搜索 project name 和 path，placeholder 明确说明搜索范围。
- Clear 按钮只清空 project 搜索。
- 可排序列固定为 Sessions、Tokens、Tools、Failed、Last Active。
- Page size 候选项固定为 25、50、100。

## 文字内容

- 页面标题固定为 `Projects`。
- 表格标题固定为 `All Projects`。
- Project 列显示项目名，副文本显示路径摘要。
- Agents 列 badge 使用 `CC`、`QD`、`CX` 或完整 agent badge，并在 tooltip 中显示完整名称。
- 无结果文案必须说明当前 project 搜索无匹配。

## 数据指标与口径

- KPI Projects：当前索引中 project key 去重数。
- KPI Sessions：所有 project 下 session 总数。
- KPI Total Tokens：所有 project 的 Fresh + Cache Read + Cache Write + Output。
- KPI Failed Tools：所有 project 的 failed tool result 数。
- 表格列固定为 Project、Agents、Sessions、Tokens、Tools、Failed、Last Active。
- Project 列使用 project name + display path；完整 path 放 tooltip。
- Agents 列按项目内出现过的 agent 拆成多个独立 badge。
- Sessions 列是该 project session 总数。
- Tokens 列使用统一 token cell。
- Tools 列展示 tool call 总数；如有失败，在同列或 Failed 列展示 failed badge。
- Last Active 使用 project 内最后 session 活跃时间。

## 交互逻辑

- 输入 project 搜索后实时或提交更新表格，匹配数量同步更新。
- 点击 Clear 清空搜索并恢复完整项目列表。
- 点击项目行或项目名进入 Project Detail。
- 点击可排序表头切换排序方向，排序状态必须可见。
- Hover project path 展示完整路径。
- Hover tokenbar 展示四类 token 数量和占比。

## 状态

- 无项目数据：展示未索引空态和可执行下一步。
- 搜索无结果：展示 Clear Search。
- token 缺失：Token cell 显示 `N/A` 并说明缺失来源。

## 禁止项

- 不出现 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
- 不把多个 agent 合并成一个 badge。
- 不让短列随宽屏无限拉伸。
