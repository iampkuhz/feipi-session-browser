# Visual Gates 参考

本文件列出 session detail UI 开发相关的视觉质量门。修改 UI 后必须根据变更范围选择对应的 gate 运行。

## Gate 列表

| Gate 脚本 | 用途 | 触发条件 |
|---|---|---|
| `check_session_detail_static.py` | Session detail 页面静态结构检查 | 改模板时必跑 |
| `check_session_detail_shell_css.py` | Session detail shell CSS 一致性检查 | 改 shell/layout CSS 时必跑 |
| `run_session_detail_interaction_gate.py` | Session detail 交互 gate（Playwright） | 改 JS handler 时必跑 |
| `run_session_detail_layout_gate.py` | Session detail 布局 gate（Playwright） | 改布局或 shell 时必跑 |
| `check_js_action_handlers.py` | JS action handler 完整性检查 | 改 JS 或模板按钮时必跑 |
| `check_css_ownership.py` | CSS ownership 校验 | 改 CSS 时必跑 |
| `check_no_legacy_css.py` | Legacy CSS 检查 | 改 CSS 时必跑 |
| `check_layout_inline_style.py` | Inline style 检查 | 改模板时必跑 |
| `check_raw_innerhtml.py` | Raw innerHTML 检查 | 改 JS 或模板时必跑 |

## 选择策略

- **只改模板 HTML**：`check_session_detail_static.py` + `check_layout_inline_style.py` + `check_raw_innerhtml.py`。
- **只改 CSS**：`check_css_ownership.py` + `check_no_legacy_css.py` + `check_session_detail_shell_css.py`（如涉及 shell）。
- **只改 JS**：`check_js_action_handlers.py` + `check_raw_innerhtml.py` + `run_session_detail_interaction_gate.py`。
- **改布局或 shell**：`run_session_detail_layout_gate.py` + `check_session_detail_shell_css.py` + `check_layout_inline_style.py`。
- **收口前**：运行全部 9 个 gate。

## Baseline 文件

- `scripts/checks/layout_inline_style_baseline.json` — 行内样式基线数据。
- `scripts/checks/innerhtml_baseline.json` — innerHTML 基线数据。

修改 baseline 前必须确认变更是有意为之，不是为了绕过 gate。
