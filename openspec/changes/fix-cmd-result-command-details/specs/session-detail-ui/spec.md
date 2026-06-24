# Session Detail UI Delta

## MODIFIED Requirements

### Requirement: Payload tab 与 modal

#### Scenario: Tool result command detail
点击 tool result 的 Result 按钮打开 payload modal 时，如果 tool parameters 中存在 `command` 或 `cmd`，Command 卡片必须展示完整未截断的指令命令。该完整指令不得使用 timeline command preview 的截断摘要替代。

如果 tool parameters 中存在 `workdir`、`cwd` 或 `working_directory`，Command 卡片必须在独立字段中展示完整工作目录，不得把工作目录拼接进 command 字符串或 summary。内嵌 payload、lazy round 注入 payload 与 `/payload/{payload_id}` JSON fallback 必须使用一致的字段与展示结构。
