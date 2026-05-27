# 跨页面交互 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 跨页面交互（侧边栏切换、分页、AJAX 部分渲染、复制操作、Profile 模态框、Timeline 交互） |
| 关联源码 | `src/session_browser/web/templates/base.html`（侧边栏）、各页面 JS |
| 关联测试 | `tests/pages/test_sidebar_toggle.py`、`test_profile_modal_open.py`、`test_timeline_expandability.py`、`test_timeline_preview.py`、`tests/rendering/test_copy_action_contract.py`、`tests/web/test_sessions_ajax_partial.py`、`tests/sessions_list/test_sessions_list_interactions.py` |
| 主要风险 | 侧边栏切换后布局不一致；AJAX 渲染与全页渲染结果不一致 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-INTERACTION-001 | P0 | interaction | 侧边栏切换（展开/折叠） | 点击侧边栏切换按钮 | body class 切换，sidebar 宽度变化，main 宽度相应调整 | pytest | — | `tests/pages/test_sidebar_toggle.py` |
| UI-INTERACTION-002 | P0 | interaction | 会话列表交互（筛选/排序/分页 AJAX） | 在列表页执行筛选/排序/分页 | URL 变化，DOM 更新正确，AJAX 响应渲染正常 | pytest | — | `tests/sessions_list/test_sessions_list_interactions.py` |
| UI-INTERACTION-003 | P0 | interaction | Sessions AJAX 部分渲染 | 发送 AJAX 请求到 sessions 端点 | 返回 HTML 片段正确渲染，无全页刷新 | pytest | — | `tests/web/test_sessions_ajax_partial.py` |
| UI-INTERACTION-004 | P0 | interaction | 分页 hasNext 逻辑 | 检查分页 hasNext 计算 | 当前页 < 总页时 hasNext=True，否则 False | pytest | — | `tests/web/test_sessions_pagination_has_next.py` |
| UI-INTERACTION-005 | P1 | interaction | 复制操作契约（data-copy 属性） | 检查含 `data-copy` 的按钮 | 点击后复制到剪贴板，按钮有正确的 data-copy 值 | pytest | — | `tests/rendering/test_copy_action_contract.py` |
| UI-INTERACTION-006 | P1 | interaction | Profile 模态框打开 | 触发 Profile 模态框打开操作 | 模态框可见，含预期内容 | pytest | — | `tests/pages/test_profile_modal_open.py` |
| UI-INTERACTION-007 | P1 | interaction | Timeline 可扩展性 | 检查 Timeline 展开/折叠 | 展开后显示详细内容，折叠后隐藏 | pytest | — | `tests/pages/test_timeline_expandability.py` |
| UI-INTERACTION-008 | P1 | visual | Timeline 预览 | 检查 Timeline 预览渲染 | 预览行显示摘要信息，状态图标正确 | pytest | — | `tests/pages/test_timeline_preview.py` |
| UI-INTERACTION-009 | P1 | interaction | 筛选脏状态管理 | 修改筛选条件但未提交 | 筛选器显示脏状态标识 | pytest | — | `tests/sessions_list/test_apply_dirty_state.py` |
| UI-INTERACTION-010 | P1 | interaction | 查询状态管理 | 验证筛选/排序/分页状态同步 | query params 与当前状态一致 | pytest | — | `tests/sessions_list/test_sessions_list_query_state.py` |
| UI-INTERACTION-011 | P2 | interaction | 键盘快捷键（空白待补充） | 待补充 E2E 测试 | 快捷键触发预期操作 | Playwright | — | 待补充 |
| UI-INTERACTION-012 | P2 | interaction | 跨页面导航流（空白待补充） | 待补充 E2E 测试 | 从列表页点击行跳转到详情页，URL 正确 | Playwright | — | 待补充 |
