# 页面功能标准 v3 验收清单

> 来源：`/Users/zhehan/Downloads/feipi-ui-page-spec-v3/checklists/page_acceptance_checklist.md`。
> 本清单配合 `docs/ui/contracts/03-page-contracts.md` 使用；当旧验收用例与 v3 目标状态冲突时，以 v3 为准。

## Dashboard

- [ ] 右上角有 agent scope selector。
- [ ] 保留 Session Trend、Token Trend、Prompt Activity Trend。
- [ ] 支持 Day / Week / Month。
- [ ] Trend 图和表格内容占据卡片 80-95% 主体空间。
- [ ] Hover 展示 dot、分类、数值、占比/变化率，且列对齐。
- [ ] 不展示 All Sessions。
- [ ] 包含 All Agents 和 Agent / Model Efficiency 表格。

## Sessions

- [ ] 搜索、过滤、排序、分页齐全。
- [ ] Tokens cell 为数字 + tokenbar + tooltip。
- [ ] 无 Dense / Columns / Export / 快捷键提示。
- [ ] 文本不重叠，短列不随宽屏无限拉伸。

## Session Detail

- [ ] 只有 Trace / Payload 两个主 tab。
- [ ] Trace 无 sidecar。
- [ ] Round 全宽，点击任意非按钮区域 toggle。
- [ ] LLM call 和 subagent call 都有 request/response attribution 入口。
- [ ] Payload 左侧选择 call，右侧展示归因和 raw payload。

## Projects

- [ ] 多 agent 显示多个 badge。
- [ ] 表格 contract 与 Sessions 一致。

## Agent Detail

- [ ] 顶部有 agent selector。
- [ ] 不存在独立 Agents 列表页。
