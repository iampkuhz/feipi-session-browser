# Sessions List 组件体系

## 目标

Sessions List 应由稳定的 UI 原始组件组装而成，而非一次性 HTML。

## 组件层级

1. `ui_primitives.html`
   - 通用 Jinja 宏：按钮、选择控件、统计药丸、可排序标题、token 单元格。

2. `sessions_list_components.html`
   - 页面级组合：页面标题、活跃过滤器、表格标题、页脚。

3. `ui-primitives.css`
   - 通用原始样式。

4. `sessions-list.css`
   - 页面作用域的布局和表格样式，限定在 `.sessions-page` 下。

5. `ui_primitives.js`
   - 小型通用行为，主要是排序按钮表单集成。

## 按钮契约

使用 `ui.btn(label, variant, size)` 或等价的 `.ui-btn` 类。

允许的变体：
- `primary`
- `secondary`

允许的尺寸：
- `sm`
- `md`

除非首先定义新的原始组件，否则避免在 Sessions List 上使用一次性按钮类。
