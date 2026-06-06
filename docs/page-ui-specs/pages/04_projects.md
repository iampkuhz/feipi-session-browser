# Projects 页面规约

## 定位

Projects 是项目级入口页，展示已索引工作区的项目活动、agent 覆盖、token 规模和失败概况，并提供进入 Project Detail 的路径。

## 页面布局

- 路由：`/projects`；模板：`projects.html`。
- Page Head 左侧显示 `Projects` 和一句工作区说明。
- KPI 区固定展示 `Projects`、`Sessions`、`Total Tokens`、`Failed Tools` 四张卡。
- Filter Card 放在 KPI 区下方，`All Projects` 表格上方。
- `All Projects` 表格占页面主宽度，支持横向滚动。

## 控件和候选项

- 搜索框只搜索 project name 和 path，placeholder 固定为 `Search project name or path`。
- Clear 按钮只清空 project 搜索。
- 可排序列固定为 `Activity`、`Tokens`、`Tools / Failure`、`Last Active`。
- Page size 候选项固定为 25、50、100。

## 文字内容

- 页面标题固定为 `Projects`。
- 表格标题固定为 `All Projects`。
- Project 列显示项目名，副文本显示路径摘要。
- Agents 列 badge 使用完整 agent badge。
- 无结果文案必须说明当前 project 搜索无匹配。

## 数据指标与口径

### KPI 区

1. `Projects`
   - 一级值：当前索引中 project key 去重数。
   - 二级指标固定为 `Active 24h`、`Active 7d`、`New 7d`。
   - `Active 24h`：最近 24 小时内有 session event 的 project 去重数。
   - `Active 7d`：最近 7 个自然日内有 session event 的 project 去重数。
   - `New 7d`：first seen timestamp 落在最近 7 个自然日内的 project 去重数。
2. `Sessions`
   - 一级值：所有 project 下 session 总数。
   - 二级指标固定为 `Today`、`7d Avg`。
   - `Today`：first user message timestamp 落在当前自然日内的 session 数。
   - `7d Avg`：最近 7 个自然日每日 session 数的算术平均值。
3. `Total Tokens`
   - 一级值：所有 project 的 `Fresh + Cache Read + Cache Write + Output`。
   - 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
4. `Failed Tools`
   - 一级值：所有 project 的 failed tool result 数。
   - 二级指标固定为 `Failure Rate`、`Affected Projects`。
   - `Failure Rate`：`Failed Tools / Tool Calls`。
   - `Affected Projects`：failed tool result 数量大于 0 的 project 数。

### All Projects 表格

- 表格列固定为 `Project`、`Agents`、`Activity`、`Tokens`、`Tools / Failure`、`Last Active`。
- `Project`：project name + display path；完整 path 放 tooltip。
  - 示例值：`feipi-session-browser · ~/Documents/tools/llm/...`。
- `Agents`：项目内出现过的 agent 拆成多个独立 badge。
  - 示例值：`Claude Code`、`Codex`。
- `Activity`：合并展示 sessions 和 active period。
  - 示例值：`842 sessions · 2026-05-01 to 2026-06-06`。
- `Tokens`：使用统一 token cell。
  - 示例值：`31.2M`，tooltip 展示 Fresh、Cache Read、Cache Write、Output。
- `Tools / Failure`：合并展示 tool calls 和 failed tool count。
  - 示例值：`8,942 tools · 108 failed`。
- `Last Active`：project 内最后 session event 时间。
  - 示例值：`2 min ago`。

## 交互逻辑

- 输入 project 搜索后防抖更新表格，匹配数量同步更新。
- 点击 Clear 清空搜索并恢复完整项目列表。
- 点击项目行和项目名进入 Project Detail。
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
