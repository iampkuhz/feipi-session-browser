# 通用 UI 规约

## Shell

- 所有页面使用统一 app shell：Sidebar、Topbar、Main、Content、Footer 结构稳定。
- Sidebar 目标主导航只包含 Dashboard、Sessions、Projects，并高亮当前页面。
- 单 agent 深度信息通过 Dashboard agent scope selector 展示；Agent Detail 不作为目标页面。
- Token Glossary 是辅助 reference 入口，不作为核心业务主导航。
- Topbar 展示面包屑和必要操作，不承载长说明文案。
- Footer 保留只读、本地运行语义；不出现营销式文案。
- 主内容区不得被 Sidebar、Topbar、Footer 遮挡；页面滚动区域必须明确。

## 页面基线

- UI 面向桌面端高密度扫描、比较和重复操作。
- Page Head 包含页面标题、短副标题、必要 stat pills 和右侧操作。
- 宽屏空间优先给主列、标题列、图表和明细表，短字段列固定宽度。
- 文本不得重叠；空间不足使用横向滚动、截断和 tooltip。
- 不用营销式 hero、大装饰卡片、布局说明、快捷键说明占用首屏。
- 不提供全局搜索入口；搜索只出现在 Sessions、Projects、Glossary 等需要检索当前列表的页面内。

## 共享组件

- Card 只承载独立信息组、重复项、modal、工具面板；页面 section 不再套大卡片。
- Button 必须有明确命令；页面内操作按钮必须有 `data-action`，跳转按钮必须有 `href`。
- 图标按钮必须有可访问名称；不熟悉图标必须有 tooltip。
- Badge 用于 Agent、Model、Provider、Status、Severity；多个值必须拆成多个独立 badge。
- Chart 必须有标题、统计口径、legend、tooltip；无数据时显示空态，不渲染空白坐标区。
- Tooltip 只解释 tokenbar、图表点、异常信号和不可用原因，不承载必须常驻的核心数据。
- Modal/Drawer 用于 payload、request、response、attribution，必须支持关闭按钮、Esc、遮罩关闭和内部滚动。

### Data Table

- `Data Table` 是所有列表表格的共享组件，固定包含 table header、table body、table footer。
- table header 固定展示表格标题、当前结果数量、当前排序字段。
- table body 固定支持横向滚动；短字段列固定宽度，长文本列使用截断和 tooltip。
- 表头排序入口覆盖整个表头单元格，hover 区域与可点击区域一致。
- 可排序表头必须展示排序方向；再次点击同列切换升序和降序。
- 行点击、行内链接、复制按钮、展开按钮的点击区域必须分离。
- table footer 固定承载 `Pagination`，不漂浮在页面视口底部。

### Compact Table

- `Compact Table` 是诊断卡片内的小型只读表格，固定包含 table header 和 table body，不包含 table footer。
- `Compact Table` 不使用 `Pagination`。
- `Compact Table` 行数固定由页面规约声明。
- `Compact Table` 只用于 Top N、信号摘要、字段映射、术语解释。
- `Compact Table` 不承载主列表检索、分页、批量浏览。
- `Compact Table` 的长文本单元格必须截断并提供 tooltip。

### Pagination

- `Pagination` 是所有分页列表的共享组件，固定包含结果范围、page size selector、previous button、page number buttons、next button、page jump input。
- 结果范围格式固定为 `Showing <start>-<end> of <total>`。
- page size selector 候选项固定由页面规约声明，默认值由页面规约声明。
- previous button 文案固定为 `Previous`；第一页时 disabled。
- next button 文案固定为 `Next`；最后一页时 disabled。
- page number buttons 固定展示当前页、前 2 页、后 2 页、第一页、最后一页；省略部分用 ellipsis 显示。
- page jump input label 固定为 `Go to page`；输入正整数并按 Enter 后跳转。
- page jump input 输入小于 1 的值时跳到第一页；输入大于总页数的值时跳到最后一页。
- 分页状态必须写入 URL 参数 `page` 和 `page_size`。

### Token Cell

- `Token Cell` 是所有 token 总量单元格的共享组件，固定由 total value、`Tokenbar`、tooltip 组成。
- total value 展示 `Fresh + Cache Read + Cache Write + Output`，缩写保留一位小数。
- total value 必须使用 tabular number。
- `Tokenbar` 固定展示四段 token 构成，顺序为 Fresh、Cache Read、Cache Write、Output。
- `Tokenbar` 每段宽度按该 token 类型占 total tokens 的比例计算。
- `Tokenbar` 总宽度固定为 88px；高度固定为 6px；圆角固定为 999px。
- `Tokenbar` tooltip 固定展示 Fresh、Cache Read、Cache Write、Output 的数量和占比，并展示 total tokens。
- token 字段缺失时 `Token Cell` 显示 `N/A`，tooltip 固定说明缺失字段和来源。
- total tokens 为 0 时 `Tokenbar` 显示空轨道，tooltip 展示四类 token 均为 0。

### Chart Tooltip

- `Chart Tooltip` 是所有图表点、图表柱、token timeline、tokenbar 的共享悬浮层。
- tooltip 外层固定宽度范围为 260px 到 360px，内容超出时内部文本换行，不撑开页面布局。
- tooltip 顶部固定为 header 行，左侧展示当前维度名称，右侧展示时间范围、round id、agent、project 中的当前图表主维度。
- tooltip 内容区固定使用 3 列 grid：label、value、share。
- label 列左对齐，带颜色点时颜色点固定 8px，文字从同一 x 位置开始。
- value 列右对齐，使用 tabular number，token 数值缩写保留一位小数。
- share 列右对齐，百分比保留一位小数；没有占比含义的行显示空白。
- 分组总计行上方固定显示 1px separator；总计行 label 为 `Total`，value 使用真实合计值。
- Fresh、Cache Read、Cache Write、Output 四类 token 行顺序固定，不随数值大小重排。
- tooltip 内的异常、fallback、缺失原因固定放在底部 note 区，note 区跨 3 列显示，最长展示 2 行。
- 键盘 focus 图表点时展示同一 tooltip 内容，Esc 关闭 tooltip。
- tooltip 不显示图表内部归一化绘图值，只显示业务真实值、占比、delta、来源和精度。

## 交互

- 页面内搜索、过滤、排序、分页必须可见、可用，并保留 URL 参数和页面状态。
- Active filters 必须可见，并支持逐项移除和一键清空。
- 可排序列必须展示当前排序方向；再次点击同列切换方向。
- 行跳转、行展开、复制、payload 查看不能互相抢占点击区域。
- Round header 和任意非按钮区域点击切换展开；全局只保留一个 Expand all / Collapse all 控制。
- 不使用 Dense、Comfortable、Columns、Export、Keyboard shortcuts 这类布局工具按钮。

## 数据和状态

- 页面必须展示数据源支持的核心字段；不可用数据必须显示原因、来源、精度，不得静默隐藏。
- 数字统一格式；token 数值缩写保留一位小数，时间格式在列表中保持可比较。
- Token 总量必须等于 Fresh、Cache Read、Cache Write、Output 的分段合计；无法相等时必须说明不可用原因。
- 长路径、session id、model 使用 mono；token 数值使用 tabular number。
- `Created` 固定表示 session created_at；created_at 缺失时使用 first event timestamp，并在 tooltip 标注 fallback。
- `Updated` 固定表示 session 最新 indexed event timestamp。
- `Duration` 固定表示最后一个可见输出 timestamp 减去 `Created`；无可见输出时使用 `Updated - Created`，并在 tooltip 标注 fallback。
- `Process Time` 固定表示主动处理耗时合计；每段从 user message timestamp 开始，到该轮最后一个 assistant output、tool result、subagent output timestamp 结束；等待下一次用户输入和人工反馈的间隔不计入。
- 无数据页面展示明确空态和可执行下一步；过滤无结果展示当前条件和清除入口。
- 404、Error、空态页使用统一状态组件，不使用营销式 hero。

## CSS 和资源

- CSS 加载顺序固定为 `tokens.css`、`base.css`、`shell.css`、`ui-primitives.css`、页面专属 CSS。
- `tokens.css` 只维护设计变量；`base.css` 只维护 reset、基础元素、typography、focus。
- `shell.css` 只维护壳层；`ui-primitives.css` 维护共享组件；页面 CSS 只维护页面布局和特有组合。
- 页面 CSS 不直接重写共享组件基础定义。
- 不新增版本化、patch、fix、overlay、alias CSS 文件。
- 当前 UI 只维护桌面端和宽屏桌面收敛规则，不维护移动端、平板专属断点。

## 质量门

- 所有页面主路由返回 status < 500。
- Session Detail 的 round lazy load、payload、attribution 数据接口返回 status < 500。
- Jinja 关键组件在 StrictUndefined 下不得 undefined。
- Browser smoke 覆盖 Dashboard All agents、Dashboard single agent、Sessions、Projects、Session Detail Trace、Session Detail Payload、Project Detail。
- 交互 smoke 固定点击排序、搜索 focus、tokenbar hover、round toggle、request/response attribution、payload call selector。
- UI 修改后按影响范围选择并运行相关 pytest、`python3 scripts/quality/run_quality_gate.py --target session-detail`、页面级 QA 脚本。
- 验证失败必须保留失败命令和原因；未运行的命令不得描述为通过，失败的命令不得描述为通过。
