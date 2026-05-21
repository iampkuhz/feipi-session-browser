# Token Glossary 页面行为合同

> 源自 HIFI 页面 `pages/token-glossary.html`（feipi-session-browser-hifi-integrated-v1）。
> 对应生产模板 `src/session_browser/web/templates/glossary.html`。
> T021 生成，2026-05-21。

## 按钮行为表

| selector | label | location | data-action-or-href | expected behavior | validation notes |
|---|---|---|---|---|---|
| `aside.sidebar button.settings[data-action="settings"]` | Settings | Sidebar footer | `data-action="settings"` | 打开 Settings 面板：展示本地数据路径、主题、快捷键与扫描配置 | `title` 属性含中文说明；`aria-label="打开设置面板"` |
| `header.topbar button.icon-button[data-action="help"]` | ❓ | Topbar 右侧 | `data-action="help"` | 打开术语页帮助说明 | `aria-label="打开术语页帮助"` |
| `header.topbar button.icon-button[data-action="shortcuts"]` | ⌨️ | Topbar 右侧 | `data-action="shortcuts"` | 打开快捷键说明面板 | `aria-label="打开快捷键说明"` |
| `.metric-grid .metric-card .info-icon` (Token Types) | ℹ️ | Token Types metric card 标签行 | `title="查看 token 分类说明"` | 打开就地说明 popover，解释 Token Types 指标含义 | inline `.info-icon`；hover 显示 tooltip |
| `.metric-grid .metric-card .info-icon` (Derived Metrics) | ℹ️ | Derived Metrics metric card 标签行 | `title="查看派生指标计算说明"` | 打开就地说明 popover，解释派生指标计算方式 | inline `.info-icon`；hover 显示 tooltip |
| `.metric-grid .metric-card .info-icon` (Provider Fields) | ℹ️ | Provider Fields metric card 标签行 | `title="查看 provider 字段映射说明"` | 打开就地说明 popover，解释 provider 字段映射 | inline `.info-icon`；hover 显示 tooltip |
| `.metric-grid .metric-card .info-icon` (Round Signals) | ℹ️ | Round Signals metric card 标签行 | `title="查看 round / step 相关信号说明"` | 打开就地说明 popover，解释 round/step 信号含义 | inline `.info-icon`；hover 显示 tooltip |
| `.legend-card .section-head .info-icon` | ℹ️ | Badge & Color Legend card 标题行 | `title="统一 Agent、Status 与 Token Segment 颜色定义"` | 打开就地说明 popover，解释图例颜色定义 | inline `.info-icon`；hover 显示 tooltip |
| `article.section-card .section-head .info-icon` (Token Composition) | ℹ️ | Token Composition section 标题行 | `title="Provider 上报的基础 token 字段"` | 打开就地说明 popover，解释基础 token 字段来源 | inline `.info-icon`；hover 显示 tooltip |
| `article.section-card .section-head .info-icon` (Derived Metrics) | ℹ️ | Derived Metrics section 标题行 | `title="由基础 token 字段计算出来的指标"` | 打开就地说明 popover，解释派生指标计算逻辑 | inline `.info-icon`；hover 显示 tooltip |
| `article.section-card .section-head .info-icon` (Provider Mapping) | ℹ️ | Provider Mapping section 标题行 | `title="从不同 provider 原始字段映射到统一字段"` | 打开就地说明 popover，解释字段映射规则 | inline `.info-icon`；hover 显示 tooltip |
| `article.section-card .section-head .info-icon` (Round Signals) | ℹ️ | Round Signals section 标题行 | `title="与 Session detail trace 视图保持一致的 round / step 术语"` | 打开就地说明 popover，解释 round/step 术语 | inline `.info-icon`；hover 显示 tooltip |
| `a.nav-link[href="#"]` (Dashboard) | Dashboard | Sidebar nav | `href="#"` | 导航到 Dashboard 页面 | `.nav-link` 无 `active` |
| `a.nav-link[href="#"]` (Sessions) | Sessions | Sidebar nav | `href="#"` | 导航到 Sessions 列表页 | `.nav-link` 无 `active` |
| `a.nav-link[href="#"]` (Projects) | Projects | Sidebar nav | `href="#"` | 导航到 Projects 列表页 | `.nav-link` 无 `active` |
| `a.nav-link[href="#"]` (Agents) | Agents | Sidebar nav | `href="#"` | 导航到 Agents 列表页 | `.nav-link` 无 `active` |
| `a.nav-link.active[href="#"]` (Token Glossary) | Token Glossary | Sidebar nav | `href="#"` | 当前页面，保持 `active` 高亮 | `.nav-link.active` |
| `input#glossary-search.filter-bar__input` | 搜索（placeholder: "搜索术语、指标、Provider…"） | 生产模板搜索卡片 | 无（input 非 button） | 输入关键词实时过滤所有 glossary-table rows，150ms debounce | 生产模板特有；HIFI 无此搜索框 |
| `span#glossary-match-count` | 匹配计数 | 搜索卡片右侧 | 无 | 显示匹配条目数，格式 "N 条匹配"；搜索为空时隐藏 | 生产模板特有 |
| `a[href="/dashboard"]` (404) | ← Dashboard | 404 state-panel 链接区 | `href="/dashboard"` | 导航回 Dashboard 首页 | 404 页面主操作 |
| `a[href="/projects"]` (404) | Projects | 404 state-panel 链接区 | `href="/projects"` | 导航到 Projects 列表页 | 404 页面辅助操作 |
| `a[href="/sessions"]` (404) | Sessions | 404 state-panel 链接区 | `href="/sessions"` | 导航到 Sessions 列表页 | 404 页面辅助操作 |
| `a[href="/agents"]` (404) | Agents | 404 state-panel 链接区 | `href="/agents"` | 导航到 Agents 列表页 | 404 页面辅助操作 |
| `a[href="/dashboard"]` (error) | ← Dashboard | error state-panel 链接区 | `href="/dashboard"` | 导航回 Dashboard 首页 | error 页面主操作 |
| `details.state-panel__details summary` (error) | Error details | error state-panel 详情区 | 无（details/summary） | 展开/折叠原始错误信息 `<pre>` 容器 | 仅当 `{{ error }}` 非空时渲染 |

## 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| 〰️ | Sidebar brand `.brand-logo` | 产品标识（波浪线/Profiler） | decorative | 无交互，纯装饰 | `--icon-size-metric` (24px) |
| 📊 | Sidebar nav `.nav-link` (Dashboard) | Dashboard 页面图标 | decorative | 跟随导航链接点击 | `--icon-size-nav` (20px) |
| 🧾 | Sidebar nav `.nav-link` (Sessions) | Sessions 页面图标 | decorative | 跟随导航链接点击 | `--icon-size-nav` (20px) |
| 📁 | Sidebar nav `.nav-link` (Projects) | Projects 页面图标 | decorative | 跟随导航链接点击 | `--icon-size-nav` (20px) |
| 🤖 | Sidebar nav `.nav-link` (Agents) | Agents 页面图标 | decorative | 跟随导航链接点击 | `--icon-size-nav` (20px) |
| 📘 | Sidebar nav `.nav-link.active` (Token Glossary) | Token Glossary 页面图标 | decorative | 跟随导航链接点击 | `--icon-size-nav` (20px) |
| ⚙️ | Sidebar footer `.settings` button | Settings 入口图标 | decorative | 跟随 Settings 按钮点击打开面板 | `--icon-size-nav` (20px) |
| › | Sidebar footer `.settings` button 右侧 | 展开/进入指示器 | decorative | 跟随 Settings 按钮点击 | `--icon-size-inline` (14px) |
| ❓ | Topbar `.icon-button[data-action="help"]` | 帮助入口 | action | 点击打开术语页帮助说明 | `--icon-size-inline` (16px) |
| ⌨️ | Topbar `.icon-button[data-action="shortcuts"]` | 快捷键入口 | action | 点击打开快捷键说明面板 | `--icon-size-inline` (16px) |
| ℹ️ | 4 个 metric card `.metric-label .info-icon` | 指标口径说明入口 | action | hover 显示 tooltip；点击打开详细说明 popover | `--icon-size-inline` (14px) |
| ℹ️ | Legend card `.section-head .info-icon` | 图例颜色定义说明入口 | action | hover 显示 tooltip；点击打开详细说明 popover | `--icon-size-inline` (14px) |
| ℹ️ | 4 个 section card `.section-head .info-icon` | 术语组说明入口 | action | hover 显示 tooltip；点击打开详细说明 popover | `--icon-size-inline` (14px) |
| 🧮 | Token Types metric card `.metric-icon.purple` | Token 分类标识（计算） | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 📐 | Derived Metrics metric card `.metric-icon.green` | 派生指标标识（测量） | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 🧩 | Provider Fields metric card `.metric-icon.orange` | Provider 字段标识（拼图） | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| 🪧 | Round Signals metric card `.metric-icon.blue` | Round 信号标识（路标） | decorative | 无交互，标识 metric 类型 | `--icon-size-metric` (24px) |
| `.dot.claude` (紫色色点) | Badge & Color Legend — Agent 行 | Claude Code 标识 | decorative | 纯装饰，图例色标 | 8-10px circle |
| `.dot.codex` (绿色色点) | Badge & Color Legend — Agent 行 | Codex 标识 | decorative | 纯装饰，图例色标 | 8-10px circle |
| `.dot.qoder` (橙色色点) | Badge & Color Legend — Agent 行 | Qoder 标识 | decorative | 纯装饰，图例色标 | 8-10px circle |
| `.dot.total` (色点) | Badge & Color Legend — Token Segment 行 | Output token 标识 | decorative | 纯装饰，图例色标 | 8-10px circle |
| 💡 | Note strip `.note-icon` | 提示/说明标识 | decorative | 无交互，页面定位说明前缀 | `--icon-size-metric` (24px) |
| `!` | error.html `.state-panel__icon--error` | 错误/异常标识 | decorative | 无交互，错误页视觉标识 | `--icon-size-metric` (24px) |
| `404` | 404.html `.state-panel__icon` | 页面未找到标识 | decorative | 无交互，404 页视觉标识 | `--icon-size-metric` (24px) |

## 统计

| 类别 | 数量 |
|---|---|
| 按钮/交互总数（HIFI glossary） | 17（3 个 topbar/sidebar 按钮 + 10 个 info icon + 4 个 nav link） |
| 按钮/交互总数（生产 glossary 新增） | 2（搜索输入 + 匹配计数） |
| 按钮/交互总数（404 + error 页面） | 6（5 个导航链接 + 1 个 details toggle） |
| 图标总数（含色点） | 24 |
| 可交互图标 | 10（10 个 ℹ️ info-icon） |
| 纯装饰图标 | 14（brand + nav + metric + legend dots + note + state icons） |

## HIFI docs/token-glossary.md 补充按钮逻辑

| 按钮 | 点击效果 |
|---|---|
| Search | 过滤所有 glossary table rows（HIFI 文档中提到但 HTML 未实现） |
| Clear Search | 清空搜索条件，恢复所有卡片和表格（HIFI 文档中提到但 HTML 未实现） |
| badge / token legend | 作为语义示例，默认不点击 |
| ℹ️ | 打开对应术语组说明 |
| Settings | 打开 Settings 抽屉 |

## HIFI docs/token-glossary.md 补充图标说明

| 图标 | 含义 | 是否可点击 |
|---|---|---|
| 📘 / 📚 | Glossary / reference | 导航或识别 |
| 🔎 | 搜索 | 输入框交互（HIFI 文档中提到但 HTML 未渲染） |
| ℹ️ | 术语组说明 | 是 |
| ✅ ⚠️ ❌ | status badge 示例 | 否 |

## 与生产模板差异备注

- 生产模板 `glossary.html` 有搜索过滤功能（`#glossary-search` + 150ms debounce + `#glossary-match-count` 计数），HIFI 页面 `token-glossary.html` 无搜索框。
- 生产模板有 `#glossary-empty` 空状态元素（搜索无匹配时显示）；HIFI 无此组件。
- 生产模板 badge 规范示范区使用 Jinja2 宏（`{{ status_success("成功") }}` 等）渲染 badge 示例，HIFI 使用纯 HTML badge + dot 元素。
- 生产模板使用 `data-table-enhanced` 表格增强；HIFI 使用 `.glossary-table` + `.wide-table` 类。
- 404 和 error 页面在生产模板中使用 `.state-panel` 组件布局，HIFI 无对应的独立 state/error 页面。
- HIFI docs 提到 Search/Clear Search 按钮，但 `token-glossary.html` 实际 HTML 中未实现。
