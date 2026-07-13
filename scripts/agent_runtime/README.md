# Agent Runtime implementation index

人类生命周期真相见 `docs/agent-runtime.md`，机器契约见
`harness/agent-runtime.manifest.yaml`。本目录只实现契约：

- `hook_entry.py`、`events/`：共享事件适配、策略与 evidence。
- `identity.py`、`paths.py`、`git_state.py`、`storage.py`：可信身份与基础能力。
- `session/`：Registry、writer lease、lifecycle、handoff 与 finalize。
- `stop/`：typed Stop context、evidence、recovery、report 与七阶段 pipeline。

平台入口不得复制这里的策略；稳定 CLI 由 `scripts/harness/` 提供。
