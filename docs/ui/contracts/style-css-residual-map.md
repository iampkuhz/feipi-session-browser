# style.css 残留规则归属图

> 生成时间：2026-05-24 | style.css 总计 ~6100 行
> 状态更新：2026-06-06 — 已确认为孤儿 CSS，待删除

## 状态

`style.css` 不被任何 HTML 模板加载。所有 ~6100 行均为孤儿 CSS，不影响线上 UI。
已确认无引用，待删除。

## 已迁移类别（本 Sprint 完成）

| 残留类别 | selector 示例 | 迁移到 | 规则数 |
|---|---|---|---|
| session-detail 页面级 | `.session-detail-phase1`, `.llm-call-card`, `.message-card`, `.tool-call-row`, `.hot-card`, `.top-rounds`, `.profile-table`, `.token-profile`, `.run-profile`, `.llm-call-detail`, `.timeline-node--llm-call` | `css/session-detail.css` | ~150 条 |
| sessions-list 页面级 | `.sessions-title-cell`, `.sessions-title-link` | `css/sessions-list.css` | 2 条 |
| 组件级 | `.data-table` 体系 | `css/ui-primitives.css` | ~140 条 |
| 组件级 | `.badge`, `.kpi`, `.card`, `.empty-state`, `.filter-bar`, `.table-wrap`, `.tab-content` | `css/ui-primitives.css` | ~60 条 |

## style.css 剩余内容（孤儿 CSS，不迁移）

| 残留类别 | selector 示例 | 行数 | 后续处理 |
|---|---|---|---|
| nav / brand | `.brand-card`, `.nav-*` | ~100 | 后续 sprint 或整体删除 |
| overview | `.overview__*` | ~100 | 后续 sprint 或整体删除 |
| timeline | `.timeline-*` 数百条 | ~500 | 后续 sprint 或整体删除 |
| payload viewer | `.viewer-*`, `.payload-viewer-overlay` | ~200 | 后续 sprint 或整体删除 |
| interaction | `.interaction-*`, `.msg-*`, `.llm-card`, `.tool-card` | ~300 | 后续 sprint 或整体删除 |
| round / trace | `.round-*`, `.trace-*`, `.span-*` | ~200 | 后续 sprint 或整体删除 |
| utility 类 | `.text-*`, `.flex`, `.gap-*`, `.mt-*`, `.mb-*` | ~100 | 后续 sprint 或整体删除 |
| responsive | `@media` 断点规则 | ~50 | 后续 sprint 或整体删除 |
| 注释残留 | orphaned comments | ~300 | 后续可清理 |
