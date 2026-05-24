# style.css 残留规则归属图

> 生成时间：2026-05-24 | style.css 总计 7921 行

## 关键发现

**`style.css` 不被任何 HTML 模板加载。**
所有 7921 行均为孤儿 CSS，不影响线上 UI。
本表用于指导如何清理和归档这些代码。

## 归属矩阵

| 残留类别 | selector 示例 | 当前文件 | 目标文件 | 是否本 Sprint 迁移 | 风险 |
|---|---|---|---|---|---|
| session-detail 页面级 | `.session-detail-phase1` (~370 条) | `style.css:7116-7487` | `css/session-detail.css` | 是 | 无（孤儿 CSS） |
| session-detail 页面级 | `.llm-call-card` (~190 条) | `style.css:7500-7689` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.message-card` (~55 条) | `style.css:7784-7839` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.tool-call-row` (~55 条) | `style.css:7719-7774` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.hot-card` (~27 条) | `style.css:1922-1974` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.top-rounds-list` / `.top-round__*` (~45 条) | `style.css:2023-2068` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.profile-table-wrap` | `style.css:2068-2136` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.llm-call-detail` (~28 条) | `style.css:3444-3472` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.token-profile__*` (~36 条) | `style.css:2393-2429` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.run-profile-bar` / `.run-profile-summary` (~20 条) | `style.css:1883-1909, 2941-2957` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.tool-hotspots` | `style.css:3045` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.timeline-node--llm-call` | `style.css:5632-5804` | `css/session-detail.css` | 是 | 无 |
| session-detail 页面级 | `.quick-access-btn` | `style.css` | `css/session-detail.css` | 是 | 无 |
| sessions-list 页面级 | `.sessions-title-cell`, `.sessions-title-link` | `style.css:2136-2140` | `css/sessions-list.css` | 是 | 无 |
| 组件级 | `.data-table` 体系 (~970 条) | `style.css:1370-2337` | `css/ui-primitives.css` | 是 | 需确认 sessions-list 是否引用 |
| 组件级 | `.badge` / `.badges` / `.badge-agent-*` | `style.css:2631-2641, 5164-5177` | `css/ui-primitives.css` | 是 | 无 |
| 组件级 | `.metric-card` / `.metrics-grid` | `style.css:436-494` | `css/ui-primitives.css` | 是 | 无 |
| 组件级 | `.table-wrap` / `.table-footer` | `style.css:499, 1771-1816` | `css/ui-primitives.css` | 是 | 无 |
| 组件级 | `.tab-content` / `.tabular` | `style.css:984, 1100-1101` | `css/ui-primitives.css` | 是 | 无 |
| 组件级 | `.card` / `.empty-state__*` | `style.css` | `css/ui-primitives.css` | 是 | 需审查是否有页面专属变体 |
| 组件级 | `.filter-bar` | `style.css` | `css/ui-primitives.css` | 是 | 无 |
| shell | `.sd-shell` / `.sd-content` | `style.css:2151-2393` | `css/shell.css`（已在 shell.css 有定义） | 否，审查后删除重复 | 需确认 shell.css 是否已覆盖 |
| tokens/base 重复 | `:root` CSS 变量 | `style.css` | `css/tokens.css` | 否，审查后删除重复 | 低 |
| legacy | `.btn` 已删除注释 | `style.css:1032` | 删除注释 | 否 | 无 |
| legacy | `.tabs` / `.tab` 已删除注释 | `style.css:1064` | 删除注释 | 否 | 无 |
| 页面级（不迁移） | `.payload-modal` | `style.css:6682 注释` | 已迁移至 `ui-primitives.css` | 否 | 已完成 |
| 页面级（不迁移） | `.hotspots-grid` | `style.css:2016` | 保留（dashboard 专属） | 否 | 待后续 sprint |
| 页面级（不迁移） | `.profile-call-index` | `style.css:2114-2127` | 保留 | 否 | 待后续 sprint |
| 页面级（不迁移） | `.profile-lazy-placeholder` | `style.css:4515` | 保留 | 否 | 待后续 sprint |
| 页面级（不迁移） | `.timeline-node--llm-call` 相关 | `style.css:5632-6136` | 保留（timeline 专属） | 否 | 待后续 sprint |
| 页面级（不迁移） | `.payload-viewer-overlay` 等 viewer | `style.css:6924-7100` | 保留 | 否 | 待后续 sprint |

## 迁移优先级

1. **P0** — session-detail 页面级（~800 条规则）
2. **P0** — sessions-list 页面级（少量）
3. **P1** — `.data-table` 组件（~970 条规则）
4. **P1** — `.badge` 组件
5. **P2** — 其他组件级（`.metric-card`, `.table-wrap`, `.tab-content`, `.card`, `.filter-bar`）
6. **P3** — shell 重复 → 删除
7. **P3** — legacy 注释 → 删除

## 不在本 Sprint 处理的残留

以下类别保留在 `style.css` 中，待后续 sprint 处理：

- 全量 timeline 体系（`.timeline-*` 数百条）
- Payload viewer overlay（`.viewer-*`, `.payload-viewer-overlay`）
- `.profile-call-index`, `.profile-lazy-placeholder`
- `.hotspots-grid`
- 工具性类（`.text-*`, `.flex`, `.gap-*`, `.mt-*`, `.mb-*` 等 utility）
- 注释残留
