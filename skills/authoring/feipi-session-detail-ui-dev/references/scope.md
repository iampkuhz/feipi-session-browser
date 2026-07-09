## 负责范围

- Session detail 页面的 Jinja / HTML 模板修改和新增。
- Session detail 相关 CSS 样式、布局、ownership 管理。
- 前端 JS action handler（按钮点击、展开折叠、交互事件绑定）。
- Session detail shell、layout、interaction 组件。
- UI 视觉质量门的维护和新增。
- Jinja macro 的复用和优化。
- CSS baseline 和 layout baseline 的更新。

## 禁止范围

- 不改后端 parser 代码（Claude Code / Codex / Qoder parser）。
- 不改 Java 产品代码（core-domain、sources、index-sqlite 等模块）。
- 不改 OpenSpec 编排或 agent runtime 配置。
- 不改 session ingestion pipeline 或 token attribution 逻辑。
- 不改 hooks、非 UI 相关的 quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不使用真实 session 做 fixture 或测试数据。

## 关键路径

1. `src/templates/` → Jinja 模板文件，session detail 页面结构。
2. `src/static/css/` → CSS 样式文件，ownership 分区。
3. `src/static/js/` → JS 交互脚本，action handler 绑定。
4. `scripts/quality/check_session_detail_static.py` → 静态检查入口。
5. `scripts/quality/check_css_ownership.py` → CSS ownership 校验。
6. `scripts/quality/check_js_action_handlers.py` → JS handler 完整性检查。
7. `scripts/quality/*_baseline.json` → UI gate baseline 数据。

## 常见误区

- 误以为可以直接添加全局 CSS 类。实际每个 CSS 规则必须有明确 ownership，通过 `check_css_ownership.py` 校验。
- 误以为 inline style 是快速修复的好方法。实际 inline style 会被 `check_layout_inline_style.py` 拦截。
- 误以为删除模板中的按钮只需改 HTML。实际必须同步删除对应的 JS action handler。
- 误以为修改 macro 只影响当前页面。实际必须检查所有调用点。
- 误以为可以用真实 session 数据做 UI 测试。实际必须使用 fixture 或 mock 数据。
- 误以为 Playwright gate skipped 等于 PASS。实际 skipped 不能描述为通过。

## 触发门禁

- `python scripts/quality/check_session_detail_static.py`
- `python scripts/quality/check_session_detail_shell_css.py`
- `python scripts/quality/run_session_detail_interaction_gate.py`
- `python scripts/quality/run_session_detail_layout_gate.py`
- `python scripts/quality/check_js_action_handlers.py`
- `python scripts/quality/check_css_ownership.py`
- `python scripts/quality/check_no_legacy_css.py`
- `python scripts/quality/check_layout_inline_style.py`
- `python scripts/quality/check_raw_innerhtml.py`
