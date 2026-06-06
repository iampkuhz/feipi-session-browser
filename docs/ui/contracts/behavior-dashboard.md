# Dashboard 页面行为合同

> 源自生产模板 `src/session_browser/web/templates/dashboard.html`。
> T016 生成，2026-05-21。

## 按钮行为表

| selector | label | location | data-action-or-href | expected behavior | validation notes |
|---|---|---|---|---|---|
| `button.nav-item[data-action="nav-dashboard"]` | Dashboard | Sidebar nav | `data-action="nav-dashboard"` | 导航到 Dashboard 页面；当前页保持 `is-active` 高亮 | `.is-active` 修饰当前页 |
| `button.nav-item[data-action="nav-sessions"]` | Sessions | Sidebar nav | `data-action="nav-sessions"` | 导航到 Sessions 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-projects"]` | Projects | Sidebar nav | `data-action="nav-projects"` | 导航到 Projects 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-agents"]` | Agents | Sidebar nav | `data-action="nav-agents"` | 导航到 Agents 列表页 | 无特殊状态 |
| `button.nav-item[data-action="nav-glossary"]` | Token Glossary | Sidebar nav | `data-action="nav-glossary"` | 导航到 Token Glossary 页 | 无特殊状态 |
| `button.nav-item.nav-item--footer[data-action="open-settings"]` | Settings | Sidebar footer | `data-action="open-settings"` | 打开 Settings 抽屉（`#settingsDrawer`），展示本地数据路径、主题、扫描配置 | `title` 属性含中文说明 |
| `button.scope-switch__btn[data-scope="day"]` | Day | Topbar 右侧 scope-switch | `data-scope="day"` | 三张趋势图切换为 Day 粒度（最近 30 天），重绘图表 | 默认 `is-active` |
| `button.scope-switch__btn[data-scope="week"]` | Week | Topbar 右侧 scope-switch | `data-scope="week"` | 三张趋势图同步切换为 Week 粒度（最近 12 周） | 互斥单选 |
| `button.scope-switch__btn[data-scope="month"]` | Month | Topbar 右侧 scope-switch | `data-scope="month"` | 三张趋势图同步切换为 Month 粒度（最近 12 月） | 互斥单选 |
| `button.icon-button--info[data-info="projects"]` | ℹ️ | Projects metric card 标签行 | `data-info="projects"` | 打开 `#infoPopover` 浮层，显示 Projects 指标口径说明 | 与 metric-card__label 同行 |
| `button.icon-button--info[data-info="sessions"]` | ℹ️ | Sessions metric card 标签行 | `data-info="sessions"` | 打开 `#infoPopover` 浮层，显示 Sessions 指标口径说明 | 与 metric-card__label 同行 |
| `button.icon-button--info[data-info="tokens"]` | ℹ️ | Total Tokens metric card 标签行 | `data-info="tokens"` | 打开 `#infoPopover` 浮层，显示 Total Tokens 指标口径说明 | 与 metric-card__label 同行 |
| `button.icon-button--info[data-info="failed-tools"]` | ℹ️ | Failed Tools metric card 标签行 | `data-info="failed-tools"` | 打开 `#infoPopover` 浮层，显示 Failed Tools 指标口径说明 | 与 metric-card__label 同行 |
| `button.icon-button--info[data-info="chart-sessions"]` | ℹ️ | Session Trend chart card 标题行 | `data-info="chart-sessions"` | 打开 `#infoPopover` 浮层，显示 Session Trend 图表口径说明 | 与 `<h2>` 标题同行 |
| `button.icon-button--info[data-info="chart-tokens"]` | ℹ️ | Token Trend chart card 标题行 | `data-info="chart-tokens"` | 打开 `#infoPopover` 浮层，显示 Token Trend 图表口径说明 | 与 `<h2>` 标题同行 |
| `button.icon-button--info[data-info="chart-prompts"]` | ℹ️ | Prompt Activity Trend chart card 标题行 | `data-info="chart-prompts"` | 打开 `#infoPopover` 浮层，显示 Prompt Activity Trend 图表口径说明 | 与 `<h2>` 标题同行 |
| `button.icon-button--ghost[data-action="chart-menu"][data-chart="sessions"]` | ⋯ | Session Trend chart card 右上角 | `data-action="chart-menu"` `data-chart="sessions"` | 打开 `#menuPopover` 菜单：导出预览、打开详情、复制链接 | `.icon-button--ghost` 透明背景 |
| `button.icon-button--ghost[data-action="chart-menu"][data-chart="tokens"]` | ⋯ | Token Trend chart card 右上角 | `data-action="chart-menu"` `data-chart="tokens"` | 打开 `#menuPopover` 菜单：导出预览、打开详情、复制链接 | `.icon-button--ghost` 透明背景 |
| `button.icon-button--ghost[data-action="chart-menu"][data-chart="prompts"]` | ⋯ | Prompt Activity Trend chart card 右上角 | `data-action="chart-menu"` `data-chart="prompts"` | 打开 `#menuPopover` 菜单：导出预览、打开详情、复制链接 | `.icon-button--ghost` 透明背景 |
| `button.icon-button[data-action="close-settings"]` | ✖️ | Settings drawer 面板头部 | `data-action="close-settings"` | 关闭 `#settingsDrawer` 抽屉 | drawer 面板右上角 |

## 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| 📈 | Sidebar brand-card `.brand-mark` | 产品标识（增长/分析） | decorative | 无交互，纯装饰 | `--icon-size-metric` (24px) |
| 📊 | Sidebar nav-item `nav-dashboard` | Dashboard 页面图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| 🗂️ | Sidebar nav-item `nav-sessions` | Sessions 页面图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| 📁 | Sidebar nav-item `nav-projects` | Projects 页面图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| 🤖 | Sidebar nav-item `nav-agents` | Agents 页面图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| 📘 | Sidebar nav-item `nav-glossary` | Token Glossary 页面图标 | decorative | 跟随导航按钮点击 | `--icon-size-nav` (20px) |
| ⚙️ | Sidebar footer nav-item `open-settings` | Settings 入口图标 | decorative | 跟随 Settings 按钮点击 | `--icon-size-nav` (20px) |
| 📁 | Projects metric-card `.metric-card__icon` | 项目数量标识 | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 🧭 | Sessions metric-card `.metric-card__icon` | 会话数量标识 | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 🪙 | Total Tokens metric-card `.metric-card__icon` | Token 总量标识 | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 🚨 | Failed Tools metric-card `.metric-card__icon` | 失败工具标识（告警） | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| ℹ️ | 4 个 metric card 标签行 `.icon-button--info` | 指标口径说明入口 | action | 点击打开 info popover，解释指标含义和计算口径 | `--icon-size-inline` (16px) |
| ℹ️ | 3 个 chart card 标题行 `.icon-button--info` | 图表口径说明入口 | action | 点击打开 info popover，解释图表数据口径 | `--icon-size-inline` (16px) |
| ⋯ | 3 个 chart card 右上角 `.icon-button--ghost` | 图表更多操作菜单 | action | 点击打开 action menu（导出预览/打开详情/复制链接） | `--icon-size-inline` + `.icon-button--ghost` (22px) |
| ✖️ | Settings drawer 头部 `.icon-button` | 关闭抽屉 | action | 点击关闭 `#settingsDrawer` | `--icon-size-inline` (16px) |
| `.legend-dot--claude` (色点) | 3 个 chart card legend row | Claude Code 数据系列色标 | decorative | hover 时无特殊行为，仅图例标识 | 8-10px circle |
| `.legend-dot--codex` (色点) | 3 个 chart card legend row | Codex 数据系列色标 | decorative | hover 时无特殊行为，仅图例标识 | 8-10px circle |
| `.legend-dot--qoder` (色点) | 3 个 chart card legend row | Qoder 数据系列色标 | decorative | hover 时无特殊行为，仅图例标识 | 8-10px circle |

## 统计

| 类别 | 数量 |
|---|---|
| 按钮总数 | 20 |
| 图标总数 | 18（含 3 个 legend 色点） |
| 可交互图标 | 8（7 个 ℹ️ + 3 个 ⋯ + 1 个 ✖️，其中 ⋯ 有 3 个实例） |
| 纯装饰图标 | 10（brand + nav + metric card） |

## 与生产模板差异备注

- 生产模板 `src/session_browser/web/templates/dashboard.html` 当前只有 4 个按钮（`range-btn`），使用 `onclick` 而非 `data-action`。
- 生产模板缺少 sidebar（由 `base.html` 提供）、scope-switch Day/Week/Month、info 图标、chart-menu 图标、Settings drawer。
- 生产模板只有 2 张图表（Session Trend + Token Trend）。
