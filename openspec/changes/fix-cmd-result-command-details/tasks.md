# Tasks: 修复 cmd result command details

按顺序执行并在完成时记录验证证据。

- [x] 1. 补齐 session-detail-ui 增量规格，明确 Result modal 的 Command 卡片必须展示完整 command 并独立展示 workdir。
  - Validation: `python3 scripts/openspec/validate_schema.py` 通过。

- [x] 2. 修改 tool result payload 构建与模板/JS 渲染，使 `cmd`/`command` 与 `workdir` 分字段进入 Command 卡片。
  - Validation: `./scripts/session-browser.sh test tests/test_session_detail_llm_attribution_ui.py -q` 通过。

- [x] 3. 增加回归测试覆盖内嵌 payload 和 `/payload` JSON 渲染路径的完整 command/workdir。
  - Validation: `./scripts/session-browser.sh test tests/test_session_detail_llm_attribution_ui.py -q` 与 `./scripts/session-browser.sh test tests/session_detail/test_tool_command_summary.py -q` 通过。

- [ ] 4. 运行 OpenSpec/harness 和本次变更触发的 required quality gates。
  - Validation: scoped `python3 scripts/quality/run_required_quality_gates.py --changed-files [...]` 通过 acceptance-contracts/harness/python-src；`run_session_detail_layout_gate.py --self-test` 与 `run_session_detail_interaction_gate.py --self-test` 通过。未勾选：默认 `python3 scripts/quality/run_required_quality_gates.py` 仍因当前 changed-files 日志中的 Java 迁移改动触发 java-src，`noJavaTestSkips`/`reuseBaselineVerify` 失败；完整 session-detail 浏览器 gate 因 fixture index 初始化缺失 `indexer.init_schema` 阻断。
