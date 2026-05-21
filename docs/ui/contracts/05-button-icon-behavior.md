# 05 Button and Icon Behavior Contract

## 全局按钮行为表要求

每个页面必须有一份按钮行为表，字段：

```text
selector / label / location / data-action-or-href / expected render behavior / validation
```

## 全局图标行为表要求

每个页面必须有一份图标行为表，字段：

```text
icon / location / semantic meaning / decorative-or-action / expected behavior / size class
```

## 常用按钮预期

- Settings：打开 settings drawer/panel。
- Info icon：打开就地说明 popover。
- More icon：打开轻量 action menu。
- Apply：提交当前筛选并刷新列表。
- Clear：清空当前筛选并刷新列表。
- Prev：跳到上一页；首页不渲染。
- Page input：输入页码并确认后跳转。
- Next：跳到下一页；尾页不渲染。
- Context / Response / Result：打开同一个 PayloadModal，切换对应内容。

## 图标尺寸

- nav icon: 18–20px。
- metric/card icon: 20–24px。
- inline action icon: 14–16px。

---

## Current State

> Scanned 2026-05-21 against repo `docs/ui/hifi/` and `src/session_browser/web/templates/`.

### HiFi 按钮总览

| 指标 | 数量 |
|---|---|
| HiFi 页面总数 | 28 个 HTML 文件 |
| 按钮总数（`<button>` + `<a.btn>`） | 240 个 |
| 含 `onclick` 的按钮 | 19 个 |
| 含 `data-action` 的按钮 | 0 个（HiFi 页面不使用 data-action 约定） |

### HiFi 按钮分布（按文件）

| 文件 | 按钮数 |
|---|---|
| `session_detail_hifi_v9_timeline_rounds_refined.html` | 19 |
| `session_detail_hifi_v11_interaction_payload_refined.html` | 19 |
| `session_browser_hifi_v15/session_detail_result_modal.html` | 18 |
| `session_browser_hifi_v15/session_detail_response_modal.html` | 18 |
| `session_browser_hifi_v15/session_detail_context_modal.html` | 18 |
| `session_browser_hifi_v15/session_detail_trace.html` | 17 |
| `hf_01_session_detail_mhtml_ready.html` | 15 |
| `prior/session_detail_hifi_v12b_modal_open_state.html` | 11 |
| `prior/session_detail_hifi_v12b_clickable_modal.html` | 11 |
| `session_detail_hifi_v12c_modal_open_subagent_tool.html` | 10 |
| `session_detail_hifi_v12c_modal_open_response.html` | 10 |
| `session_detail_hifi_v12c_clickable_response_blocks.html` | 10 |
| `hf_05_full_payload_viewer.html` | 9 |
| `hf_04_hotspots_view.html` | 9 |
| `hf_03_calls_view.html` | 9 |
| `sessions_list_hifi_v3_no_hero.html` | 8 |
| `session_detail_v17/index.html` | 5 |
| `session_browser_hifi_v15/sessions_list.html` | 5 |
| `hf_02_sessions_list.html` | 5 |
| `dashboard_v16/dashboard.html` | 4 |
| `dashboard_v16_tooltip_dots/dashboard.html` | 4 |
| `session_detail_v18/index.html` | 3 |
| `session_browser_hifi_v15/dashboard.html` | 2 |
| `session_browser_hifi_v15/projects_overview.html` | 1 |

### 生产环境按钮总览

| 指标 | 数量 |
|---|---|
| 生产模板按钮总数 | 35 个 |
| `<button>` 缺少 `data-action` | 16 个 |
| `<a.btn>` 缺少 `href` | 0 个 |
| 含 `onclick` 的按钮 | 10 个 |

### 生产环境按钮分布（按文件）

| 文件 | 按钮数 |
|---|---|
| `components/viewer.html` | 8 |
| `components/session_detail_timeline_v12.html` | 6 |
| `dashboard.html` | 4 |
| `components/session_detail_timeline.html` | 4 |
| `base.html` | 3 |
| `partials/sessions_grid.html` | 2 |
| `components/sessions_list_components.html` | 2 |
| `projects.html` | 1 |
| `project.html` | 1 |
| `components/ui_primitives.html` | 1 |
| `components/session_detail_payload_v17_guidance.html` | 1 |
| `components/session_detail_payload_v15.html` | 1 |
| `components/data_table.html` | 1 |

### 需要修复的生产按钮

- **16 个 `<button>` 缺少 `data-action`**：主要集中在 `viewer.html`（8 个）、`dashboard.html`（4 个）、`ui_primitives.html`（1 个模板宏）、`data_table.html`（1 个）、`project.html`（1 个）、`projects.html`（1 个）。
- **10 个 `onclick` 违规**：`viewer.html`（4 个 inline onclick）、`dashboard.html`（4 个）、`project.html`（1 个）、`projects.html`（1 个）。这些违反了合同要求的 `data-action` 驱动行为模式。

### 合同合规性评估

| 合同要求 | HiFi 状态 | 生产状态 |
|---|---|---|
| 每个页面有按钮行为表 | 无（需补充） | 无（需补充） |
| 每个页面有图标行为表 | 无（需补充） | 无（需补充） |
| 按钮使用 data-action 或 href | HiFi 使用 onclick | 16/35 缺少 data-action |
| 按钮无 inline onclick | 19/240 有 onclick | 10/35 有 onclick |
| 图标尺寸分级 | 未见显式尺寸 class | 未见显式尺寸 class |

