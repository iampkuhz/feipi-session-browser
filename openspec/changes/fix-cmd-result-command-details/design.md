# Design: cmd result command details

## 当前状态
`_build_payload_lookup()` 和 Session Detail view model 在注册 tool result payload 时把 `tool_command` 设置为 `_build_tool_command_summary()` 的结果。该 helper 面向 timeline preview，会截断 Bash 命令；对于 `exec_command` 等未知工具会把参数前几个 key/value 拼成一段摘要，例如 `cmd=... workdir=...`，导致 modal 中 Command 卡片既不完整，也无法区分工作目录。

## 方案
1. 在 render helper 中新增 tool result command detail helper，从 tool parameters 中提取完整 `command/cmd` 与 `workdir/cwd/working_directory`。
2. tool result payload 注册时使用完整 command 字段，并额外写入 `tool_workdir`；没有可识别 command 时才回退到现有 summary，保持旧工具可见性。
3. payload 模板的 Command 卡片改为结构化字段：`command` 用 `<pre>` 展示完整命令，`workdir` 独立展示完整工作目录。
4. `payloadNodeFromJson()` 使用相同字段渲染动态 API/lazy payload，保证 slim page 和 full payload fetch 行为一致。

## 风险
- 超长命令会增加 modal 内容长度；该内容只在用户打开 payload 时展示，且沿用 modal 滚动容器。
- 非 shell 类工具没有 command 字段时仍走 summary 回退，避免空白 Command 卡片。

## 回滚
回退 helper、payload 注册字段、模板和 JS 渲染改动后，将恢复原先只展示 `tool_command` summary 的行为。

## 验证
- `python3 scripts/openspec/validate_layout.py`
- `python3 scripts/openspec/validate_schema.py`
- `python3 scripts/openspec/validate_active_change.py --change-id fix-cmd-result-command-details`
- `python3 scripts/harness/validate_harness_structure.py`
- `python3 -m pytest tests/test_session_detail_llm_attribution_ui.py -q`
- `python3 -m pytest tests/session_detail/test_tool_command_summary.py -q`
- `python3 scripts/quality/run_required_quality_gates.py`
