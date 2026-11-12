# Sessions 页面规约

- 列表仅保留 `Task Active`，不展示 `Wall Duration` 列；底层计时和其他页面不变。使用当前 row 的 typed `timing`，缺来源显示 `N/A`，不回退 legacy 数字。任务窗口非模型执行的说明常驻表格旁。

- 总量 stat pill 与每行 Token Cell 遵循 `common.md` 的 `Token Measurement Provenance`；估算带 `≈`，缺来源/未上报不伪装成实测 0。

## 定位

Sessions 是完整 session 检索和浏览页，负责让用户按 session、project、agent、model、失败状态和时间快速定位运行记录。该页是明细列表页，必须优先保证搜索、过滤、排序、分页和行跳转的稳定性。

## 页面布局

- 路由：`/sessions`；模板：`sessions.html`。
- Page Head 左侧显示 `Sessions` 和一句浏览说明；右侧不放全局搜索。
- Page Head stat pills 固定展示 `Sessions`、`Projects`、`Total Tokens`。
- Page Head 下方是 Filter Card，Filter Card 下方是 `All Sessions` 表格。
- 标准宽度下内容区宽度随主栏变化；宽屏主栏可用宽度达到 1600px 以上时，Sessions 内容区必须继续扩展到宽屏最大宽度，不能保持窄桌面视觉宽度不变。
- `All Sessions` 使用通用 `Data Table` 组件。
- `All Sessions` 表格区域必须支持横向滚动，不能压缩列导致文本重叠。
- `All Sessions` 底部分页器使用通用 `Pagination` 组件。

## 控件和候选项

- 搜索框只搜索当前 Sessions 列表，placeholder 固定为 `Search title, project, agent, model, session id`。
- Agent 过滤候选项固定包含 `All Agents`、`Claude Code`、`Qoder`、`Codex`。
- Model 过滤候选项来自当前索引中出现过的 model，默认 `All Models`。
- Project 过滤候选项来自当前索引中出现过的 project，默认 `All Projects`。
- Status/failure 过滤候选项固定为 `All`、`Failed`、`No failures`。
- Reset 按钮清空搜索和过滤，保留默认排序。
- Reset 按钮必须和搜索框、Agent、Model、Project、Status 下拉筛选框保持在同一行；标准桌面宽度下不得被挤到独立一行。
- Agent、Model、Project、Status 下拉筛选框使用紧凑宽度，长值在控件内截断并保留原始下拉选项。
- Page size selector 候选项固定为 25、50、100，默认值固定为 25。

## 文字内容

- 页面标题固定为 `Sessions`。
- 表格标题固定为 `All Sessions`。
- Active filters 使用字段名 + 当前值，例如 `Agent: Claude Code`。
- Active filters 只展示 Agent、Model、Project、Status 过滤条件，不展示搜索框 `Search:` chip。
- 过滤无结果文案必须说明当前过滤条件无匹配，并提供 Clear All Filters。
- 默认空态文案必须说明未索引 session。

## 数据指标与口径

### Page Head stat pills

- `Sessions`：当前过滤条件下的 session 总数；未应用过滤时等于已索引 session 总数。
- `Projects`：当前过滤条件下的 project key 去重数。
- `Total Tokens`：当前过滤条件下 `Fresh + Cache Read + Cache Write + Output` 的合计。

### All Sessions 表格

- 表格列固定为 `Session`、`Project`、`Agent`、`Model`、`Tokens`、`Rounds`、`Tools`、`Subagents`、`Task Active`、`Created`、`Updated`。
- `Session`：主标题使用更大、更深的文字，最多两行；短 ID 与 branch 使用次级小字，不能抢占标题层级。
  - 优先展示 API 的纯文本 `displayTitle`，缺该字段时使用 `title`；空白、只有当前 session ID / session key / 短 ID 或 UUID 的标题显示 `Untitled session`，保留次级 ID 区分会话。
  - 过长标题两行截断，标题链接保留完整文本 tooltip 与可访问名称；过长 branch 单行截断并提供完整 tooltip，短 ID tooltip 保留完整 ID。
  - 标题和整行仍可进入 Session Detail，不改标题搜索数据。
- `Project`：展示 project name，tooltip 展示完整 cwd。
  - 示例值：`feipi-session-browser`。
- `Agent`：展示标准 agent badge。
  - 示例值：`Claude Code`。
- `Model`：展示 model mono 文本。
  - 示例值：`claude-sonnet-4.5`。
  - 过长时截断并提供 tooltip。
- `Tokens`：使用通用 `Token Cell`，展示 total tokens。
  - 示例值：`184k`。
  - hover/键盘 focus 弹框仅展示 Fresh input、Cache read、Cache write、Output 四行，每行类别、独立占比条、数量、占比同排并对齐；不重复放大总量堆叠条或独立 `Shown total` 行。
  - 占比仍以单元格当前所示总量为分母，已知零显示 `0.0%`，未知不画占比、不伪装为零；保留测量来源、估算和未知说明。Enter 可打开，Escape 可关闭。
- `Rounds`：仅简化标题，保留现有 logical groups / observed model call boundaries / partial / unknown 口径及排序。
  - 示例值：`18`。
- `Tools`：合并 tool call 总数和失败数，按 tool call 总数排序，不按失败数排序。
  - 已知 100 次调用、5 次失败显示 `100(5)`；已知无失败仅显示 `100`。
  - 失败数未知显示 `100(?)`，总数也未知显示 `—(?)`；仅失败数已知时可显示 `—(5)`。tooltip 和可访问名称明确说明各自未知状态，不将未知当 0。
- `Subagents`：展示 subagent call 数。
  - 示例值：`2`。
  - 来源字段缺失时显示 `N/A` 并在 tooltip 说明来源缺失。
- `Task Active`：展示 typed MAIN source task-window union，缺测显示 `N/A`；不是模型执行。
  - 示例值：`9m 42s`。
  - 存在可定位主任务窗口，同时存在不完整或无法配对任务时，保留 `Partial` 按钮；点击或键盘 Enter/Space 可查看含义，Escape 关闭说明，不能触发行跳转。
  - Partial 值只覆盖可定位的主任务窗口，重叠部分只计一次，包含窗口内 tools/waits；不是完整会话耗时或模型推理时间。无可用窗口是 `N/A`，不显示 Partial。
- `Created`：展示通用时间指标 `Created`。
  - 示例值：`2026-06-06 10:24`。
- `Updated`：展示通用时间指标 `Updated`。
  - 相对时间按秒、分钟、小时、天选择单位，固定一位小数，例如 `12.5s ago`、`2.5m ago`、`1.3h ago`、`2.5d ago`；tooltip 保留原始时间戳。排序仍使用原始时间戳。

## 交互逻辑

- 输入搜索后防抖更新结果，URL 保留 `q`。
- 修改过滤器后结果更新，URL 保留对应过滤参数。
- Active filter 的单项移除只删除该过滤条件，不清空其它条件。
- 可排序列固定为 `Tokens`、`Rounds`、`Tools`、`Subagents`、`Task Active`、`Created`、`Updated`。Sessions 页面和资源 API 对手工传入的 `sort=failure` / `sort=duration` 回退到 Updated 降序，不影响 Project Detail 的排序。
- 默认排序固定为 `Updated` 降序。
- 点击可排序表头切换升序/降序，并保留搜索、过滤和 page size。
- 翻页保留搜索、过滤、排序和 page size。
- 点击 session 行或 session 标题进入 Session Detail；点击后必须立即给当前行可见的打开中反馈，并发起详情页导航。
- Session Detail 首屏必须优先返回 Hero KPI、诊断卡和 Trace 摘要行；重型 round detail、payload 和 attribution 内容按需加载，避免从列表页进入详情页时长时间停留在列表页。
- 点击 Project 列链接进入 Project Detail。
- 行内复制按钮只复制目标值，不触发行跳转。
- `Tokenbar` hover/focus 使用本页紧凑明细布局；列表单元格仍保留总量和缩略堆叠条，其他页面的 Token Cell 不变。

### 合成示例：标题优化前后

以下均为合成数据，不来自真实 session。

| 场景 | 优化前 | 优化后 |
| --- | --- | --- |
| 长标题 | `修复合成订单服务的缓存失效与重复扣款，并补充…` 单行截断 | 主标题最多两行，完整标题可聚焦/悬浮查看；`synthetic-0 · feature/synthetic-checkout-cache-regression` 为次级信息 |
| 短标题 | `Add synthetic checkout validation` 与辅助信息层级接近 | 深色 14px 主标题；`synthetic-1 · main` 使用更小的次级字 |
| 仅 ID | 主标题 `synthetic-2`，下方再次显示 ID | 主标题 `Untitled session`，下方保留 `synthetic-2` |
| 标题缺失 | 用 session ID 充当标题 | 主标题 `Untitled session`，仍可通过次级 ID、项目、时间与详情入口辨识 |

## 状态

- 默认无数据：展示未索引空态和可执行下一步。
- 过滤无结果：展示当前条件和 Clear All Filters。
- 搜索 focus：边框和轻量阴影清晰可见。
- token 缺失：Token cell 显示 `N/A`，tooltip 说明字段不可用。

## 禁止项

- 不出现 Dense、Comfortable、Columns、Export、Keyboard shortcuts。
- Token cell 内不出现多行 legend 和无意义 `tokens` 文案。
- 不隐藏核心列来换取视觉留白。

- Token bar 使用共享分列弹框（见 `common.md`），不再维护 Sessions 专属进度轨道布局；保持当前列表总量分母和来源状态。
