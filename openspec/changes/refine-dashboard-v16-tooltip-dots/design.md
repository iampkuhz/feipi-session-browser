# Design: Dashboard v16 Tooltip Dots

## 架构

当前实现：JS 生成 `.bar` 元素，tooltip 通过 `.bar::after` 伪元素 + `content: attr(data-tip)` 渲染纯文本。

新实现：JS 在每个 `.bar` 内部渲染 `.dashboard-tooltip` DOM，通过 `.bar:hover .dashboard-tooltip` 控制显隐。

## 变更文件

| 文件 | 操作 |
|---|---|
| `dashboard.html` | 修改 JS tooltip 生成逻辑，输出结构化 DOM |
| `dashboard-v16-tooltip-dots.css` | 新增/合并到 `dashboard-v16.css` |
| `test_dashboard_v16.py` | 新增 tooltip DOM 结构测试 |
| `scripts/qa/ui/check_dashboard_v16_tooltip_dots.py` | 新增 QA 静态检查 |

## Tooltip DOM 结构

```html
<div class="bar" style="--h:...">
  <div class="bar-stack">...</div>
  <div class="dashboard-tooltip">
    <div class="tooltip-date">05-17</div>
    <div class="tooltip-row">
      <i class="tooltip-dot tooltip-dot--claude"></i>
      <span class="tooltip-label">Claude Code</span>
      <b class="tooltip-value">15</b>
    </div>
    ...
  </div>
</div>
```

## CSS 策略

将 `dashboard-v16-tooltip-dots.css` 中的 tooltip 相关样式合并到 `dashboard-v16.css`，保持单一 CSS 文件。

## 数据流

Session Trend tooltip 数值直接使用 `d.claude_count`, `d.codex_count`, `d.qoder_count`, `d.total_count`。
Token Trend tooltip 数值使用计算后的 `d.claude_tokens`, `d.codex_tokens`, `d.qoder_tokens`, `d.total_tokens` 并通过 `formatTokens()` 格式化。
