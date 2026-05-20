# Spec: Dashboard UI — Tooltip Dots

## 需求

1. **Session Trend tooltip** — 悬停柱状图时显示结构化 tooltip，包含日期、每个 agent 的 session 数量（带颜色圆点）和总计。
2. **Token Trend tooltip** — 同上，但值为 token 消耗，使用 M/K/B 单位格式化。
3. **颜色映射** — Claude Code: purple (#8b5cf6), Codex: green (#10b981), Qoder: orange (#f59e0b), Total: gray (#cbd5e1)。
4. **数据来源** — 所有值必须来自后端传递给 chart 的数据，不得硬编码。
5. **实现方式** — 必须使用结构化 DOM（`.dashboard-tooltip`），不能仅依赖 `title` 或 `data-tip` 属性。

## 验收标准

- `/dashboard` 返回 HTTP 200
- HTML 包含 `.dashboard-tooltip`、`.tooltip-row`、`.tooltip-dot--claude` 等 class
- Tooltip 包含 "Claude Code"、"Codex"、"Qoder"、"Total" 标签
- Session Trend 和 Token Trend 都有 tooltip 结构
- QA 脚本 `check_dashboard_v16_tooltip_dots.py` 通过
