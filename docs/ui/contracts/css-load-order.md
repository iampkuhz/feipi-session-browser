# CSS 加载顺序契约

**版本**: P0 (2026-05-24)
**状态**: 记录 + BLOCK gate

---

## 当前 CSS 加载顺序

### base.html 固定顺序

所有页面通过继承 `base.html` 获得以下 CSS 加载顺序：

1. `/static/style.css` — 设计令牌 + shell 布局骨架
2. `/static/css/ui-primitives.css` — 共享原子组件（按钮、徽章、卡片、Modal 等）
3. `/static/css/legacy-aliases.css` — 迁移兼容层，不得新增引用
4. `{% block head_extra %}` — 页面专用 CSS，通过模板继承注入

详见 `src/session_browser/web/templates/base.html:28-40`。

### 页面专用 CSS（通过 head_extra）

| 页面模板 | CSS 文件 |
|---|---|
| `dashboard.html` | `css/dashboard.css` |
| `sessions.html` | `css/ui-primitives.css` (重复) + `css/sessions-list.css` |
| `session.html` | `css/session-detail.css` |
| `projects.html` / `project.html` | `css/projects.css` |
| `agents.html` | `css/agents.css` |
| `glossary.html` | `css/glossary.css` |
| `404.html` / `error.html` | `css/states.css` |

---

## 规则

1. **tokens/base 必须早于 shell/primitives**：`style.css` 包含 `--sidebar`、`--inspector` 等核心设计令牌，必须在所有其他 CSS 之前加载。

2. **primitives 必须早于 page CSS**：`ui-primitives.css` 中的原子组件必须在页面专用 CSS 之前加载，以确保页面 CSS 可以覆写 primitive 样式。

3. **legacy-aliases.css 只允许作为迁移兼容层**：不得新增对该文件的引用。后续迁移完成后应删除。

4. **page CSS 必须通过 head_extra 在 base CSS 之后加载**：禁止在 `head_extra` 之外加载页面专用 CSS。

5. **不允许页面重复加载 base 已加载过的 CSS**：base.html 已加载 `style.css`、`ui-primitives.css`、`legacy-aliases.css`，页面不得在 `head_extra` 中重复加载。

---

## 已知问题

### sessions.html 重复加载 ui-primitives.css

`src/session_browser/web/templates/sessions.html:18` 在 `head_extra` 中再次加载了 `ui-primitives.css`：

```html
<link rel="stylesheet" href="/static/css/ui-primitives.css">
```

该文件已在 base.html:29 全局加载。重复加载无功能性作用，仅增加网络请求。

**处理**: 本 P0 仅记录，标记为 P1 后续修复项。不在本次顺带修改。

---

## Static Gate: css-load-order-contract

`scripts/quality/static_contract_check.py` 检查 `base.html` 中 CSS link 顺序必须为：

1. `/static/style.css`
2. `/static/css/ui-primitives.css`
3. `/static/css/legacy-aliases.css`
4. `{% block head_extra %}`

顺序变化则 **BLOCK**。
