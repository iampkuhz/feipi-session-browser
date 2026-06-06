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
- Data table 表头排序入口覆盖整个表头单元格，hover 区域与可点击区域一致。
- Token cell 固定为总量数字 + tokenbar；tooltip 展示 Fresh、Cache Read、Cache Write、Output 的数量和占比。
- Chart 必须有标题、统计口径、legend、tooltip；无数据时显示空态，不渲染空白坐标区。
- Tooltip 只解释 tokenbar、图表点、异常信号和不可用原因，不承载必须常驻的核心数据。
- Modal/Drawer 用于 payload、request、response、attribution，必须支持关闭按钮、Esc、遮罩关闭和内部滚动。

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
- 交互 smoke 至少点击排序、搜索 focus、tokenbar hover、round toggle、request/response attribution、payload call selector。
- UI 修改后按影响范围选择并运行相关 pytest、`python3 scripts/quality/run_quality_gate.py --target session-detail`、页面级 QA 脚本。
- 验证失败必须保留失败命令和原因；未运行的命令不得描述为通过，失败的命令不得描述为通过。
