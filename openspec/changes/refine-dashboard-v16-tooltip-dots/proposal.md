# Proposal: Dashboard v16 Tooltip Dots Refinement

## 目标

在 Dashboard 的 Session Trend 和 Token Trend 图表中，将柱状图悬停 tooltip 从纯文本（`data-tip` / `title`）升级为结构化 DOM，每一行增加对应颜色圆点，提升 agent 识别效率。

## 变更范围

- 仅修改 Dashboard 页面
- 不改动 Sessions 列表页
- 不改动 Session detail payload/modal

## 核心需求

1. Session Trend 悬停显示每个 agent 的 session 数量，带颜色圆点
2. Token Trend 悬停显示每个 agent 的 token 消耗（格式化如 4.8M），带颜色圆点
3. 颜色映射：Claude Code=purple, Codex=green, Qoder=orange, Total=gray
4. 数据来自后端 chart 数据，不硬编码
