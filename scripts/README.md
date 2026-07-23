# Scripts 维护入口

公开入口以 `harness/manifest.yaml` 为机器真相；本文只提供短索引。

- 产品与本地开发：`./scripts/session-browser.sh <command>`
- Harness 体检：`bash scripts/harness/doctor.sh`
- 三平台 Hook：settings/config 直接调用 `scripts/harness/hook_dispatch.py`
- Session/Registry CLI：`python3 scripts/harness/sessionctl.py bootstrap|set-change|list|status|doctor|cleanup|...`
- Change lifecycle：`python3 scripts/harness/change.py ensure-session|status|on-stop|resume|next-change|adopt-current|abort`
- Gate：`python3 scripts/gates/cli.py --tier quick|required|full`
- 共享 checks：`python3 -m scripts.checks <check-id>`
- OpenSpec validators：`python3 scripts/openspec/validate_{layout,schema}.py`

目录职责：`agent_runtime/` 实现共享 Runtime，`gates/` 负责 catalog/plan/execute/receipt，
`checks/` 提供无 trigger 的领域规则，`harness/` 只提供公开适配入口，`hooks/` 提供仓库策略。
Runtime 生命周期见 `docs/agent-runtime.md`；Gate 修改流程见 `scripts/gates/README.md`。
Stop 以 run-scoped Gate quality summary、receipt 和 controller attestation 作为完成证据；
已退役的共享 runtime report 不是 doctor 或本次 Gate 的前置输入。

Change completion 只有 `scripts/harness/change.py` 一个公开 CLI，平台链路固定为 dispatcher →
`scripts/agent_runtime/hook_entry.py` → controller。`sessionctl` 的 `begin-change`、`adopt-current`、
`completion-status`、`stop`、`finalize`、`handoff` 已退役；不要为旧命令增加 alias 或 wrapper。

不得直接把内部 Runtime/Gate 模块、测试、临时路径或历史脚本当公开入口。非平凡受保护改动先
复用 OpenSpec change；Stop/handoff 前唯一 required 命令是
`python3 scripts/gates/cli.py --tier required`。
