# Agent Runtime implementation index

人类生命周期真相见 `docs/agent-runtime.md`，机器契约见
`harness/agent-runtime.manifest.yaml`。本目录只实现契约：

- `hook_entry.py`、`events/`：共享事件适配、策略与 evidence。
- `identity.py`、`paths.py`、`git_state.py`、`storage.py`：可信身份与基础能力。
- `session/`：legacy run identity、writer lease、bootstrap 与 handoff 查询。
- `change/`：唯一 Session/Change/Attempt controller、CAS store、bounded runtime、candidate、fixture 与协议。
- `stop/`：仅保留平台 Stop 所需的 Git/runtime evidence，不提供 lifecycle 入口。

平台入口不得复制这里的策略；唯一稳定 Change CLI 是 `scripts/harness/change.py`，Hook 链为
`scripts/harness/hook_dispatch.py` → `hook_entry.py` → `change/controller.py`。
