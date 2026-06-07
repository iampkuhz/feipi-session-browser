# Agent Runtime Contract

本文件是 Claude Code、Codex、Qoder 在本仓库内复用的 agent 运行契约。`.claude/`、`.codex/`、`.qoder/` 只保留工具自身需要的薄入口；可复用的规则、质量目标、stop 门禁和 handoff 约束必须放在 `harness/`、`scripts/harness/`、`scripts/quality/` 或 `scripts/claude_hooks/`。

## Stop 门禁

- 三类 agent 的 Stop 入口都应调用 `scripts/harness/agent_stop_check.py`。
- Stop 门禁必须同时读取 `tmp/agent_logs/current/changed-files.jsonl` 和 `git status --short --untracked-files=all`。
- `changed-files.jsonl` 用于捕获 Write/Edit/MultiEdit；`git status` 用于捕获 Bash 删除、非 Claude agent 修改和未记录的文件变更。
- Stop 门禁必须通过 `scripts/claude_hooks/classify.py` 计算 quality target，再通过 `scripts/quality/run_required_quality_gates.py` 执行。
- changed files 只能用于判断本次必须执行哪些 quality target；一旦 target 被选中，target 内部必须执行完整 required gate baseline，不得再按 changed files 裁剪 gate。
- required gate 失败时，Stop 门禁必须阻断。失败不得因为“不是当前 agent 的改动”“已有失败”“与本次改动无关”而被降级、跳过或描述为通过。
- 如果 required gate 因外部环境缺失无法运行，状态必须保持 blocked/fail，并在输出中保留可复现命令和阻断原因。

## 契约用例门禁

- `docs/acceptance-contracts/**` 或 `tests/**` 发生变化时，必须触发 `acceptance-contracts` quality target。
- `acceptance-contracts` target 必须运行 `scripts/quality/validate_acceptance_contracts.py`。
- 测试代码中的 `contract_case` ID 必须能在 `docs/acceptance-contracts/features/*.md` 找到；活跃自动化用例也必须有测试绑定。

## Agent 入口职责

- `.claude/hooks/*.sh`、`.codex/hooks/*.sh`、`.qoder/hooks/*.sh` 只负责定位仓库根目录并转发到共享脚本。
- agent-specific subagent 定义只保留工具面、模型、权限和简短角色差异。
- subagent handoff 字段、验证命令选择和质量目标映射不得在多个 agent 入口中复制维护；需要长期复用时应沉淀到本文件或 `AGENTS.md`。
