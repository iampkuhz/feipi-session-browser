# CSS 所有权契约

> 本文件定义项目 CSS 文件的职责边界和选择器权限，防止页面 CSS 越权修改 shell 层和原语层样式。
> 对应质量门禁：`check_css_ownership.py`、`static_contract_check.py`

## 所有权矩阵

| 文件 | 允许定义 | 禁止定义 |
|---|---|---|
| `tokens.css` | CSS 自定义属性（`--xxx`）包裹在 `:root` 中 | 任何选择器规则（如 `.btn`、`body`） |
| `base.css` | `html`/`body` 重置、通配符、基础排版、HTML 元素样式 | 页面级选择器（如 `.sessions-page`）、组件类（如 `.btn`） |
| `shell.css` | `.shell`、`.app-shell`、sidebar/main/inspector grid、body state（`hide-left`/`hide-right`/`focus`） | 页面内容组件（如 `.card`、`.btn`、`.data-table`） |
| `ui-primitives.css` | 全局组件：`.btn`/`.badge`/`.modal`/`.payload-modal`/`.data-table`/`.tabs`/`.card`/`.toast`/`.tooltip`/`.popover` | 页面专属选择器（如 `.dashboard-page`、`.sd-*`） |
| `session-detail.css` | `.sd-*`、`.session-detail-*` 选择器 | shell grid 规则、原语根组件（如 `.btn` 裸定义） |
| `dashboard.css` | `.dashboard-page` 及其后代选择器 | shell grid、原语根组件 |
| `sessions-list.css` | `.sessions-page` 及其后代选择器 | shell grid、原语根组件 |
| `legacy-aliases.css` | 当前遗留变量别名（仅 `:root` 中的 `--old: var(--new)`） | 新组件定义、非变量映射规则 |

## 阻断规则

### BLOCK（新增即阻断）

1. **CSS 所有权越权**：页面 CSS 定义 shell grid（如 `.shell { grid-template-columns: ... }`）
2. **原语组件重写**：页面 CSS 直接重写原语根组件（如 `.payload-modal {}`、`.data-table {}`、`.btn {}`）
3. **新 `!important`**：任何新增的 `!important` 声明
4. **新 `innerHTML =`**：JS 中新增原始 `innerHTML` 赋值（清空操作除外）
5. **新 `.style.xxx =` 布局赋值**：JS 中新增 `el.style.display/width/position/... =` 布局操作
6. **新遗留选择器引用**：新增引用遗留别名类名
7. **新 ID 选择器**：新增 `#xxx` CSS 选择器（存量白名单除外）
8. **选择器深度越界**：新选择器嵌套深度 > 3

### WARN（存量技术债务，允许但应治理）

1. 存量 `!important`（如果存在）
2. 存量 `innerHTML` 使用
3. 存量 `.style.xxx` 布局赋值
4. 存量遗留选择器引用
5. 存量 ID 选择器（白名单内）
6. 存量选择器深度 = 3

## JS 反绕过规则

JS 文件禁止以下模式来绕过 CSS 所有权：

- `element.innerHTML = "<html>..."` — 应使用 `textContent` 或安全 helper
- `element.style.display = "none"` — 应使用 class 切换
- `element.style.position = "absolute"` — 应使用 CSS 类
- 任何直接通过 `.style` 设置 layout 相关属性的行为

例外：CSS custom property 注入（如 `el.style.setProperty('--x', '...')`）是允许的。
