# CSS 加载顺序契约

**版本**: P1 (2026-05-24)
**状态**: 记录 + BLOCK gate

---

## 当前 CSS 加载顺序

### base.html 固定顺序

所有页面通过继承 `base.html` 获得以下 CSS 加载顺序：

0. `/static/css/tokens.css` — 设计令牌（CSS 变量）
1. `/static/css/base.css` — reset、html、body、typography、focus、reduced motion
2. `/static/css/shell.css` — shell 布局骨架（Grid 三栏、body 状态切换、响应式断点）
3. `/static/css/ui-primitives.css` — 共享原子组件（按钮、徽章、卡片、Modal 等）
4. `/static/css/legacy-aliases.css` — 迁移兼容层，计划删除
5. `{% block head_extra %}` — 页面专用 CSS，通过模板继承注入

详见 `src/session_browser/web/templates/base.html:28-42`。

> `style.css` 已于 v8 sprint 删除。其原有内容由 MHTML 导出时通过 `mhtml.py` 的 `get_css()` 拼接 modular CSS 文件获得。

### 页面专用 CSS（通过 head_extra）

| 页面模板 | CSS 文件 |
|---|---|
| `dashboard.html` | `css/dashboard.css` |
| `sessions.html` | `css/sessions-list.css` |
| `session.html` | `css/session-detail.css` |
| `projects.html` / `project.html` | `css/projects.css` |
| `agents.html` | `css/agents.css` |
| `glossary.html` | `css/glossary.css` |
| `404.html` / `error.html` | `css/states.css` |

---

## 规则

1. **tokens 必须最先加载**：`css/tokens.css` 包含所有核心设计令牌（CSS 变量），必须在所有其他 CSS 之前加载。

2. **base 必须紧随 tokens 之后**：`css/base.css` 包含 reset、html、body、typography、focus 等基础样式，依赖 tokens 中的变量。

3. **shell 必须早于 primitives/page CSS**：`shell.css` 依赖 `tokens.css` 中的令牌，必须在 primitives 和页面 CSS 之前加载。

4. **primitives 必须早于 page CSS**：`ui-primitives.css` 中的原子组件必须在页面专用 CSS 之前加载，以确保页面 CSS 可以覆写 primitive 样式。

4. **legacy-aliases.css 只允许作为迁移兼容层**：后续迁移完成后删除。

5. **page CSS 必须通过 head_extra 在 base CSS 之后加载**：禁止在 `head_extra` 之外加载页面专用 CSS。

6. **不允许页面重复加载 base 已加载过的 CSS**：base.html 已加载 `tokens.css`、`base.css`、`shell.css`、`ui-primitives.css`、`legacy-aliases.css`，页面不得在 `head_extra` 中重复加载。**BLOCK**。

7. **payload-modal 裸定义应收敛至 ui-primitives.css**：在 `session-detail.css`、`legacy-aliases.css` 等处出现裸 `.payload-modal` 或 `#payload-modal` 定义时输出 **WARN**，不 BLOCK。

8. **shell 级选择器不应出现在页面 CSS**：`.app-shell`、`.shell`、`body.hide-left` 等选择器应归属 `shell.css`，页面 CSS 出现时输出 **WARN**，不 BLOCK。

---

## Static Gate 状态

| 检查 | 级别 | 说明 |
|---|---|---|
| !important | BLOCK | 禁止任何 !important |
| css-load-order | BLOCK | base.html 中 CSS link 顺序 |
| no-dead-css | BLOCK | 无 0 规则 CSS 文件 |
| no-duplicate-base-css | BLOCK | 页面不重复加载 base CSS |
| payload-modal ownership | WARN | 裸定义应收敛至 ui-primitives.css |
| shell ownership | WARN | shell 选择器不应在页面 CSS |
