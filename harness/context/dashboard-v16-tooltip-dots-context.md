# Dashboard v16 Tooltip Dots Context

Reference high fidelity file:

```text
docs/ui/hifi/dashboard_v16_tooltip_dots/dashboard.html
```

The tooltip should be implemented as real DOM markup inside each bar, not as plain `title` text.

Recommended markup:

```html
<div class="dashboard-bar">
  <div class="dashboard-bar__stack">...</div>
  <div class="dashboard-tooltip">
    <div class="tooltip-date">05-17</div>
    <div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span>Claude Code</span><b>15</b></div>
    <div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span>Codex</span><b>3</b></div>
    <div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span>Qoder</span><b>0</b></div>
    <div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span>Total</span><b>18</b></div>
  </div>
</div>
```

Token Trend uses the same structure, but values are formatted token values such as `4.8M`.
