# State Pages（404 / Error）行为合同

> 源自生产模板 `src/session_browser/web/templates/404.html` 和 `error.html`。
> HIFI 集成包中无对应的独立 404/error 页面（已记录在 `03-page-contracts.md`：「State Pages: unified primitive — no dedicated 404 HiFi」）。
> T021 生成，2026-05-21。

## 按钮行为表

| selector | label | location | data-action-or-href | expected behavior | validation notes |
|---|---|---|---|---|---|
| `a.state-panel__link[href="/dashboard"]` (404) | ← Dashboard | 404 state-panel 链接区 | `href="/dashboard"` | 导航回 Dashboard 首页 | 主操作链接，使用 `&larr;` 前缀 |
| `a.state-panel__link[href="/projects"]` (404) | Projects | 404 state-panel 链接区 | `href="/projects"` | 导航到 Projects 列表页 | 辅助操作 |
| `a.state-panel__link[href="/sessions"]` (404) | Sessions | 404 state-panel 链接区 | `href="/sessions"` | 导航到 Sessions 列表页 | 辅助操作 |
| `a.state-panel__link[href="/agents"]` (404) | Agents | 404 state-panel 链接区 | `href="/agents"` | 导航到 Agents 列表页 | 辅助操作 |
| `a.state-panel__link[href="/dashboard"]` (error) | ← Dashboard | error state-panel 链接区 | `href="/dashboard"` | 导航回 Dashboard 首页 | 主操作链接，使用 `&larr;` 前缀 |
| `details.state-panel__details summary` (error) | Error details | error state-panel 详情区 | 无（HTML `<details>/<summary>`） | 展开/折叠原始错误信息 `<pre class="state-panel__raw">` 容器 | 仅当 `{{ error }}` 非空时渲染；`{% if error %}` 守卫 |

## 图标行为表

| icon | location | semantic meaning | decorative-or-action | expected behavior | size class |
|---|---|---|---|---|---|
| `404` (文本) | 404.html `.state-panel__icon` | 页面未找到标识 | decorative | 无交互；作为视觉标识展示错误码 | 由 `.state-panel__icon` CSS 控制尺寸 |
| `!` (文本) | error.html `.state-panel__icon.state-panel__icon--error` | 服务器错误/异常标识 | decorative | 无交互；作为视觉标识展示错误状态 | 由 `.state-panel__icon--error` CSS 控制颜色（红色/告警色） |

## 页面结构

### 404.html

```
.state-panel
├── .state-panel__icon          → "404"（纯文本作为图标容器）
├── .state-panel__title         → "Page Not Found"
├── .state-panel__desc          → "The page you're looking for doesn't exist or has been removed."
├── .state-panel__links
│   ├── a.state-panel__link[href="/dashboard"]   → "← Dashboard"
│   ├── a.state-panel__link[href="/projects"]    → "Projects"
│   ├── a.state-panel__link[href="/sessions"]    → "Sessions"
│   └── a.state-panel__link[href="/agents"]      → "Agents"
```

### error.html

```
.state-panel
├── .state-panel__icon.state-panel__icon--error  → "!"（纯文本作为图标容器）
├── .state-panel__title         → "Something Went Wrong"
├── .state-panel__desc          → {{ error }}（Jinja2 变量）
├── .state-panel__links
│   └── a.state-panel__link[href="/dashboard"]   → "← Dashboard"
└── {% if error %}
    └── details.state-panel__details
        ├── summary               → "Error details"
        └── pre.state-panel__raw  → {{ error }}（原始错误信息）
    {% endif %}
```

## 统计

| 类别 | 数量 |
|---|---|
| 导航链接总数（404） | 4 |
| 导航链接总数（error） | 1 |
| details toggle（error） | 1 |
| 图标/标识总数 | 2（404 文本 + ! 文本） |
| 可交互元素 | 0（全部为链接或原生 details 元素，无按钮） |

## 与 HIFI 差异备注

- **HIFI 无独立 404/error 页面**：`feipi-session-browser-hifi-integrated-v1/pages/` 中无对应的 state/error 页面 HTML。
- HIFI `03-page-contracts.md` 中记录：「State Pages: unified primitive — Confirmed; `.state-strip` pattern used across pages — PASS (no dedicated 404 HiFi)」。
- 生产 `.state-panel` 组件与 HIFI `.state-strip` 组件语义一致，但 DOM 结构不同。
- 404 页面提供 4 个导航链接（Dashboard + 3 个核心页面），error 页面只提供 1 个（Dashboard）。
- error 页面的 `{{ error }}` 变量同时显示在描述区和 details 展开区（如果非空）。

## 已知风险

1. **无 HIFI 参考**：404/error 页面没有 HiFi 设计稿作为对照，行为合同完全基于生产模板推导。
2. **图标使用纯文本**：`.state-panel__icon` 使用 `404` 和 `!` 文本而非图标字体/emoji，与全局图标合同中的尺寸分级（nav/metric/inline）不一致。
3. **缺少 data-action**：导航链接使用 `<a>` 而非 `button[data-action]`，符合链接语义但不符合按钮合同（这些本身就是链接而非按钮）。
4. **Agent 页面链接缺失于 error**：error 页面只有 Dashboard 一个链接，而 404 有 4 个——用户从错误页恢复的路径较少。
