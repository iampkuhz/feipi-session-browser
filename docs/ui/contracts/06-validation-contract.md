# 06 验证要求

## 验证入口

- 页面功能修改后运行相关 pytest 或 Playwright 检查。
- UI 静态检查入口：`python3 scripts/qa/ui/check_ui_contracts.py`。
- CSS ownership 检查入口：`python3 scripts/quality/check_css_ownership.py`。
- Session Detail 质量门入口：`python3 scripts/quality/run_quality_gate.py --target session-detail`。

## 必查内容

- 页面必须加载当前 CSS 和 JS 文件。
- 不允许版本化、补丁、overlay、fix 文件名作为页面资源。
- 不允许移动端和平板断点成为当前 CSS 支持面。
- Dashboard、Sessions、Projects、Session Detail 的核心控件必须可见。
- 表格排序、过滤、分页和行跳转必须可执行。
- Payload modal 必须可打开、关闭、复制和滚动。

## 文档对齐

- 修改页面行为时必须同步更新 `docs/ui/`。
- 修改 `docs/ui/` 时必须评估模板、CSS、JS、测试是否需要调整。
- 不允许代码行为和 `docs/ui/` 要求长期不一致。

## 失败处理

- 验证失败必须记录失败命令和失败原因。
- 不得把未运行或失败的验证描述为通过。
- 若失败来自既有问题，必须标明与本次改动的关系。
