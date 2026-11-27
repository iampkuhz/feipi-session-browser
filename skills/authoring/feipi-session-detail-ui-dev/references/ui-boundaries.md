# Session Detail UI 边界

- Pebble 模板在 `java/web/src/main/resources/templates/`。修改 macro 前检查调用点；不要在模板中嵌入 style 或 raw `innerHTML` 脚本。
- CSS 在 `java/web/src/main/resources/static/css/`，由组件归属管理；复用现有类，不添加无归属的全局样式或 ID selector。
- 前端 JS 在 `java/web/src/main/resources/static/js/`。同步修改模板触发元素和 handler，样式状态通过 CSS class 切换。
- Shell 影响所有子组件；验证实际布局，不用隐藏内容绕过断言。基线更新只用于确认有意保留的例外，命令见 [视觉规则](visual-gates.md)。
- 自动化测试和入仓截图使用合成 fixture，覆盖受影响的真实交互；授权本机样例复核遵循[原文核对规则](../../feipi-privacy-redaction-dev/references/redaction-policy.md#本机原文核对)。
