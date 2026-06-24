# Proposal: 修复 cmd result modal 的 command 信息

## 问题
Session Detail 中点击 cmd/exec_command 的 Result 按钮后，payload modal 的 Command 卡片只展示了截断后的 command summary；对于 Codex `exec_command` 这类参数同时包含 `cmd` 和 `workdir` 的工具，当前 UI 还把两者当作一个字符串摘要合并展示，无法查看完整指令和工作目录。

## 范围
- tool result payload 保留完整 command/cmd 文本，不再使用 timeline preview 的截断摘要作为 modal 内容。
- Command 卡片内区分展示完整指令命令与工作目录。
- 同步模板内嵌 payload、lazy payload 注入和 `/payload/{payload_id}` JSON 渲染路径。

## 非目标
- 不改变 timeline 行里的 command preview 截断策略。
- 不改变 tool result 文本本身的 byte budget 和 token estimate 规则。
- 不重构 parser 或 normalized domain schema。

## 用户影响
用户在 Result modal 中可以直接查看 cmd 执行的完整命令和对应工作目录，便于复盘执行上下文和复制排查。

## 验证策略
- 增加/更新 Session Detail UI 单元测试，覆盖内嵌 payload 与 API payload 中完整 `cmd`、独立 `workdir` 字段。
- 运行 OpenSpec layout/schema/active-change、harness gate、相关 pytest，以及本次变更触发的 required quality gates。
