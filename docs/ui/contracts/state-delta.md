# State Pages Delta 文档：生产模板 vs HIFI（当前快照）

> 对比源：`src/session_browser/web/templates/404.html`、`error.html`（生产）
> vs `/Users/zhehan/Downloads/feipi-session-browser-hifi-integrated-v1/`（HIFI）
> T167 创建，2026-05-22

---

## 0. HIFI 状态/错误页面覆盖情况

| 检查项 | 结果 |
|---|---|
| HIFI pages/ 中有 404/500/error 专用页面 | **无** |
| HIFI assets/ 中有 error/state 专用资源 | **无** |
| HIFI common-hifi-rules.css 中有 .state-strip/.error-state 样式 | **无** |
| HIFI 页面内嵌空状态组件 | 有（`.state-strip`，见 project-detail.html:130、projects.html:130、session-list.html:128） |

**结论**：HIFI 没有独立的 404/500 错误页面。HIFI 仅在业务页面内使用 `.state-strip` 组件表示空状态/过滤无结果状态（inline empty state），不覆盖独立的 HTTP 错误页面。

---

## 1. 已完成迁移（无需再改）

| # | 生产元素 | 说明 |
|---|---|---|
| D1 | `404.html` 模板 | 使用 `base.html` 继承 + `.state-panel` 居中布局 |
| D2 | `error.html` 模板 | 使用 `base.html` 继承 + `.state-panel` + `<details>` 展开错误详情 |
| D3 | `.state-panel` CSS | 定义在 `style.css`（第 2861-2924 行），含居中面板、图标、标题、链接 |
| D4 | `routes.py` 路由 | `_send_404()` → 404.html；`_send_500(error)` → error.html |
| D5 | `.state-strip` 空状态组件 | `ui-primitives.css` 中定义，HIFI 对齐（用于页面内空状态，非独立错误页） |

---

## 2. 结构差异（HIFI 无对应页面）

不适用 — HIFI 无独立的 404/500 错误页面。生产端 `.state-panel` 为自研组件，无 HIFI 参照。

---

## 3. 样式差异

| # | 差异点 | 生产 CSS | HIFI CSS | 影响文件 |
|---|---|---|---|---|
| W1 | `.state-panel` 独立错误页容器 | 定义在 `style.css`（居中面板，max-width: 520px） | 不存在 | style.css |
| W2 | `.state-strip` 页面内空状态 | 定义在 `ui-primitives.css`（flex 布局，48px 图标） | HIFI 内联 HTML 使用同名 class，无独立 CSS 文件 | ui-primitives.css |
| W3 | 错误态 `.state-panel__icon--error` | `color: var(--status-error)`，36px | 不存在 | style.css |

---

## 4. 行为差异

| # | 差异点 | 生产 | HIFI | 影响文件 |
|---|---|---|---|---|
| B1 | 404 页面导航链接 | 4 个链接：Dashboard / Projects / Sessions / Agents | 不适用 | 404.html |
| B2 | 500 错误详情展开 | `<details>` + `<summary>` 折叠面板 | 不适用 | error.html |
| B3 | Jinja2 错误变量注入 | `{{ error }}` 动态渲染 | 不适用 | error.html |

---

## 5. Missing in production（HIFI 有但生产没有）

不适用 — HIFI 无独立的 404/500 错误页面，无对应可迁移项。

---

## 6. Production-only（生产有但 HIFI 没有 -- 保留不删）

| # | 独有点 | 生产实现 | 保留理由 |
|---|---|---|---|
| P1 | `404.html` 独立错误页 | `.state-panel` 居中面板 + 4 个导航链接 | HTTP 404 标准响应页，必要基础设施 |
| P2 | `error.html` 通用错误页 | `.state-panel` + Jinja2 `{{ error }}` 动态注入 + `<details>` 详情展开 | HTTP 500 标准响应页，必要基础设施 |
| P3 | `.state-panel` CSS 组件 | `style.css` 中完整定义（图标/标题/描述/链接/折叠面板） | 独立错误页视觉载体 |
| P4 | `states.css` / `states.js` 引用 | `base.html` 第 21/144 行引用；`states.css` 已存在，`states.js` 已创建（T169，IIFE stub，页面为纯静态无 JS 行为） | 引用已满足，无 404 风险 |

---

## 7. 迁移优先级与行动项

### 不适用

HIFI 无独立的 404/500 错误页面，State Pages 不在 HIFI 参考范围内。
生产端 `.state-panel` 组件为自有实现，无 HIFI delta 需要对齐。

### 建议后续关注（非本任务范围）

| # | 关注项 | 说明 | 文件 |
|---|---|---|---|
| N1 | `base.html` 中 `states.js` 缺少 `<script src>` 引用 | 文件已创建（T169），但 `base.html` 仅在注释中提及，未实际加载；如需可添加引用 | base.html |
| N2 | `.state-panel` 与 `.state-strip` 命名统一 | 两套状态组件 class 命名不同（BEM vs flat），后续可考虑统一 | style.css + ui-primitives.css |
| N3 | 500 页导航链接 | error.html 仅有 Dashboard 一个返回链接；可考虑与 404.html 对齐增加 Projects/Sessions/Agents | error.html |

---

## 8. 差异统计

| 分类 | 数量 |
|---|---|
| 已完成迁移 | 5 |
| 结构差异（HIFI 无对应） | 不适用 |
| 样式差异 | 3 |
| 行为差异 | 3 |
| Missing in production | 不适用 |
| Production-only（保留） | 4 |
| 后续关注项 | 3 |
