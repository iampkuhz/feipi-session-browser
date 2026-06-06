# Sessions 页面规约

## 定位

Sessions 是完整 session 检索和浏览页，负责让用户按 session、project、agent、model、失败状态和时间快速定位运行记录。该页是明细列表页，必须优先保证搜索、过滤、排序、分页和行跳转的稳定性。

## 页面布局

- 路由：`/sessions`；模板：`sessions.html`。
- Page Head 左侧显示 `Sessions` 和一句浏览说明；右侧不放全局搜索。
- Page Head stat pills 固定展示 `Sessions`、`Projects`、`Total Tokens`。
- Page Head 下方是 Filter Card，Filter Card 下方是 `All Sessions` 表格。
- 表格区域必须支持横向滚动，不能压缩列导致文本重叠。
- Pagination 固定在表格卡片底部。

## 控件和候选项

- 搜索框只搜索当前 Sessions 列表，placeholder 固定为 `Search title, project, agent, model, session id`。
- Agent 过滤候选项固定包含 `All Agents`、`Claude Code`、`Qoder`、`Codex`。
- Model 过滤候选项来自当前索引中出现过的 model，默认 `All Models`。
- Project 过滤候选项来自当前索引中出现过的 project，默认 `All Projects`。
- Status/failure 过滤候选项固定为 `All`、`Failed`、`No failures`。
- Reset 按钮清空搜索和过滤，保留默认排序。
- Page size 候选项固定为 25、50、100。

## 文字内容

- 页面标题固定为 `Sessions`。
- 表格标题固定为 `All Sessions`。
- Active filters 使用字段名 + 当前值，例如 `Agent: Claude Code`。
- 过滤无结果文案必须说明当前过滤条件无匹配，并提供 Clear All Filters。
- 默认空态文案必须说明未索引 session。

## 数据指标与口径

### Page Head stat pills

- `Sessions`：当前过滤条件下的 session 总数；未应用过滤时等于已索引 session 总数。
- `Projects`：当前过滤条件下的 project key 去重数。
- `Total Tokens`：当前过滤条件下 `Fresh + Cache Read + Cache Write + Output` 的合计。

### All Sessions 表格

- 表格列固定为 `Session`、`Project`、`Agent / Model`、`Tokens`、`Workload`、`Failure`、`Updated`。
- `Session`：展示 session title、短 session id、git branch。
  - 示例值：`Refine dashboard spec · a8120f1d · main`。
  - title 为空时显示 `Untitled`。
- `Project`：展示 project name，tooltip 展示完整 cwd。
  - 示例值：`feipi-session-browser`。
- `Agent / Model`：同一单元格展示 agent badge 和 model mono 文本。
  - 示例值：`Claude Code · claude-sonnet-4.5`。
  - model 过长时截断并提供 tooltip。
- `Tokens`：使用统一 token cell，展示 total tokens；tooltip 展示 Fresh、Cache Read、Cache Write、Output。
  - 示例值：`184k`。
- `Workload`：合并展示 rounds、tools、subagents、duration。
  - 示例值：`18 rounds · 42 tools · 2 subagents · 36m`。
  - Subagents 缺失时显示 `subagents N/A` 并在 tooltip 说明来源缺失。
- `Failure`：展示 failed tool result 数量。
  - 示例值：`3 failed`。
  - 没有失败时显示 `No failures`。
- `Updated`：使用 last event time，列表内格式一致。
  - 示例值：`2 min ago`。

## 交互逻辑

- 输入搜索后防抖更新结果，URL 保留 `q`。
- 修改过滤器后结果更新，URL 保留对应过滤参数。
- Active filter 的单项移除只删除该过滤条件，不清空其它条件。
- 可排序列固定为 `Tokens`、`Workload`、`Failure`、`Updated`。
- `Workload` 排序使用 rounds，其次使用 tools。
- 点击可排序表头切换升序/降序，并保留搜索、过滤和 page size。
- 翻页保留搜索、过滤、排序和 page size。
- 点击 session 行进入 Session Detail。
- 点击 Project 列链接进入 Project Detail。
- 行内复制按钮只复制目标值，不触发行跳转。
- Tokenbar hover 展示四类 token 数量、占比和总量。

## 状态

- 默认无数据：展示未索引空态和可执行下一步。
- 过滤无结果：展示当前条件和 Clear All Filters。
- 搜索 focus：边框和轻量阴影清晰可见。
- token 缺失：Token cell 显示 `N/A`，tooltip 说明字段不可用。

## 禁止项

- 不出现 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
- Token cell 内不出现多行 legend 和无意义 `tokens` 文案。
- 不隐藏核心列来换取视觉留白。
