# Agent Runtime Contract

本文件是 Claude Code、Codex、Qoder 在本仓库内复用的 agent 运行契约。`.claude/`、`.codex/`、`.qoder/`、`.agents/` 只保留工具自身需要的薄入口或链接；可复用的 skill、规则、质量目标、Stop 门禁和 handoff 约束必须放在 `skills/`、`harness/`、`scripts/harness/`、`scripts/quality/` 或 `scripts/claude_hooks/`。

## Skill 入口

- 仓库共享 skill 真源放在 `skills/<skill-name>/SKILL.md`。
- 需要目录分层的正式 skill 使用 `skills/<layer>/<skill-name>/SKILL.md`。
- Codex repo-scope skill 必须通过 `.agents/skills/<skill-name>` 链接到共享真源，因为 Codex 扫描 `.agents/skills`。
- `.codex/skills/<skill-name>` 可作为 Codex 目录约定入口，但不得作为唯一发现路径。
- `.claude/skills/<skill-name>` 链接同一共享真源；Claude Code 专属 skill 可以继续留在 `.claude/skills/`。

## 渐进式加载路由

- 仓库结构和本地运行态边界：`harness/context/repo-map.md`。
- UI 页面、CSS、前端 JS 和视觉验证：`harness/context/ui-context.md`。
- OpenSpec 变更生命周期：`harness/workflow/change-lifecycle.md`。
- subagent 委派和 handoff：`harness/workflow/subagent-execution.md`。
- required gate summary 语义：`harness/quality/deterministic-quality-gate.md`。
- target 到 gate 的路线：`harness/quality/quality-gate-matrix.md`。

## Subagent 策略

- 主 agent 应积极寻找可委派边界：长任务、并行探索、独立 QA、日志/大输出隔离、OpenSpec 规划、UI 评审、迁移分析。
- 简单单文件小改、无明确 scope、需要强串行推理、或多个 agent 会写同一文件时，不委派。
- 调用前必须提供 `Goal`、`Task id`、`Task source`、`Allowed files/directories`、`Forbidden files/directories`、`Required context files`、`Expected output`、`Validation command`、`Failure policy`。
- 可写 subagent 必须有不重叠写范围；只读 subagent 不得修改文件。

## Stop 门禁

- 三类 agent 的 Stop 入口都应调用 `scripts/harness/stop_entry.py`。
- Stop 门禁在 hook stdin 提供 `session_id` / `agent_id` 时，必须只按 `tmp/agent_logs/<client>/<session-id>/main/` 或 `tmp/agent_logs/<client>/<session-id>/agents/<agent-id>/` 下的当前 identity evidence 判断 read-only；不得因其他并发 agent 的 dirty worktree 触发当前只读 session 的门禁。
- Stop hook 无法识别当前 session 时必须 fail-closed，继续读取 session base commit 以来的 git diff 和 untracked paths，避免未归因修改绕过 target 路由。
- `changed-files.jsonl` 用于捕获 Write/Edit/MultiEdit/NotebookEdit 和 Bash mutation evidence；Bash evidence 由 PreToolUse 快照与 PostToolUse/Failure 对比产生。
- 有 changed files 的 Stop 门禁必须先获取 shared stop-check lock；锁被占用时返回 blocked/retry，不得并发运行第二组修复或 required quality gates。
- Stop 门禁必须通过 `scripts/claude_hooks/classify.py` 计算 quality target，再通过 `scripts/quality/run_required_quality_gates.py` 执行。
- changed files 只能用于判断本次必须执行哪些 quality target；一旦 target 被选中，target 内部必须执行完整 required gate baseline，不得再按 changed files 裁剪 gate。
- required gate 失败时，Stop 门禁必须阻断。失败不得因为“不是当前 agent 的改动”“已有失败”“与本次改动无关”而被降级、跳过或描述为通过。
- 如果 required gate 因外部环境缺失无法运行，状态必须保持 blocked/fail，并在输出中保留可复现命令和阻断原因。


## 主 session 并行和 runtime capability

`harness/agent-runtime.manifest.yaml` 是 hook/platform/config 的 machine-readable 真源；`harness/agent-runtime.md` 只解释真源含义，不手工维护另一份不一致矩阵。`scripts/quality/check_agent_runtime_manifest.py` 校验 manifest 引用的路径存在，`scripts/quality/check_agent_hook_parity.py` 校验 `.codex/hooks.json`、`.qoder/settings.json` 与 manifest 绑定一致。

- primary session parallelism 指多个主 agent session（例如 Qoder task A + Codex task B）各自拥有 `client/session_id/runId/worktree/branch`，可以并行推进不同任务。
- subagent multi-agent 只是主 session 内的委派；subagent 继承父 `runId`，不能创建新的 primary writer lease。
- read-only direct launch 未经 `sessionctl` 绑定，只允许只读查询；写入受 hook 阻断，对应 runtime capability 为 `read-only-ready` 或 `blocked`，不得描述成 writable。
- writable launch 必须通过 `python3 scripts/harness/sessionctl.py create/start/bind-session`，bind 后写入 hook activation marker，确认 config hash、session id、worktree root、branch 和 base commit。
- worktree/branch ownership 由 run record 和 writer lease 表达；同 worktree、同 branch 或写范围重叠的 active writer 会被 doctor 判为 `blocked`。
- hook trust/activation 依赖 checked-in wrapper、Git-root stable command、activation marker、marker TTL 和当前 config hash；删除 marker 或改坏 config path 必须阻断。
- OpenSpec per-run：`changeId` 存在于 run record 和 run-scoped `active_change.json` mirror，不能靠全局临时文件表达并发状态。
- resource locks 统一放在 `FEIPI_AGENT_RUNTIME_ROOT/locks`，runtime 输出放在 run-scoped 目录，避免多个主 session 互相覆盖。
- handoff/cleanup 只汇报状态、diff、质量证据和风险；默认 dry-run cleanup，不自动 commit、merge、push 或删除 worktree。

Runtime doctor 输出 capability，而不是笼统 PASS：

```text
writable-ready       # writable run 已绑定 session、hook marker 未过期且 config hash 匹配
read-only-ready      # read-only run 合法但没有 writer lease
blocked              # run record、worktree、writer lease、activation marker 或配置不满足 contract
read-only-ready      # 没有 sessionctl run record 的直接启动只能只读；写入阻断
```

本地目标 UX 示例（不启动真实客户端）：

```text
# Qoder task A
python3 scripts/harness/sessionctl.py create --client qoder --task-id task-a --change-id support-parallel-primary-sessions --allowed-path docs/a
python3 scripts/harness/sessionctl.py start --run-id <qoder-run> --print-command

# Codex task B
python3 scripts/harness/sessionctl.py create --client codex --task-id task-b --change-id support-parallel-primary-sessions --allowed-path docs/b
python3 scripts/harness/sessionctl.py start --run-id <codex-run> --print-command
```

`--print-command` 只打印待人工执行的环境变量和命令模板；不要把未实际启动、未 bind-session、未产生 activation marker 的客户端描述为已验证成功。

## Agent hook 配置矩阵

Claude Code 的 hook 真源是 `.claude/settings.json`：

| 事件 | 匹配器 | 入口脚本 |
|---|---|---|
| `SessionStart` | 无 | `.claude/hooks/session-start.sh` |
| `SubagentStart` | 无 | `.claude/hooks/subagent-start.sh` |
| `PreToolUse` | `Bash` | `.claude/hooks/pre-bash.sh` |
| `PreToolUse` | `Write|Edit|MultiEdit|NotebookEdit` | `.claude/hooks/pre-write.sh` |
| `PostToolUse` | `Bash` | `.claude/hooks/post-bash.sh` |
| `PostToolUse` | `Write|Edit|MultiEdit|NotebookEdit` | `.claude/hooks/post-write.sh` |
| `PostToolUseFailure` | 无 | `.claude/hooks/tool-failure.sh` |
| `Stop` | 无 | `.claude/hooks/stop.sh` |
| `SubagentStop` | 无 | `.claude/hooks/subagent-stop.sh` |
| `ConfigChange` | 无 | `.claude/hooks/config-change.sh` |

Codex 的 hook 真源是 `.codex/hooks.json`：

| 事件 | 匹配器 | 入口脚本 |
|---|---|---|
| `PreToolUse` | `Bash` | `.codex/hooks/pre_tool_guard.sh` |
| `PostToolUse` | `Bash` | `.codex/hooks/post_bash_guard.sh` |
| `PostToolUse` | `Write|Edit|MultiEdit` | `.codex/hooks/post_tool_guard.sh` |
| `Stop` | 无 | `.codex/hooks/stop_check.sh` |

Qoder 的 hook 真源是 `.qoder/settings.json`；所有 command 通过 `git rev-parse --show-toplevel` 定位仓库根后转发到 `.qoder/hooks/*.sh` wrapper，避免相对 cwd 脆弱路径。pre/post wrapper 复用 Codex-compatible guards，Stop wrapper 调用统一 stop runner。

`.claude/agents/*.md` 与 `.codex/agents/*.toml` 不定义 per-agent hooks；项目级 hooks 是唯一执行面。

## 契约用例门禁

- `docs/acceptance-contracts/**` 或 `tests/**` 发生变化时，必须触发 `acceptance-contracts` quality target。
- `acceptance-contracts` target 必须运行 `scripts/quality/validate_acceptance_contracts.py`。
- 测试代码中的 `contract_case` ID 必须能在 `docs/acceptance-contracts/features/*.md` 找到；活跃自动化用例也必须有测试绑定。

## Java 质量生命周期

- `java-src` target：`java/**/src/**/*.java` 变更触发，运行 `javaCheck`、`javaChineseComments`、`noJavaTestSkips`。
- `java-build` target：`build-logic/**`、`gradle/**`、`build.gradle.kts`、`settings.gradle.kts`、`gradle.properties` 变更触发，运行 `javaCheck`。
- `java-src` 包含 `java-build`（dominance）：避免两个 target 各自运行一次 Gradle baseline。
- Java 注释必须通过中文近似校验，术语允许英文；术语表变更需单独列出理由。
- Javadoc Day 0：production type、public method、public constructor 必须中文 Javadoc；核心字段和 record component 必须说明业务语义。
- Java 测试 0 skipped、0 aborted、非预期 0 discovered 时失败。
- 精简质量栈：javac、Spotless、Checkstyle、DocLint、PMD、ArchUnit、JUnit、JaCoCo；禁止 Error Prone、Lombok、preview。
- artifact freshness：Gradle build cache 和 configuration cache 复用 daemon；普通任务不执行 clean；仅 checkpoint 执行完整冷构建。
- 本地有界并行：Gradle class-level fork 并行，JUnit 方法级并行关闭；建议 fork 数 `min(4, max(1, CPU/2))`。LLM 调用严格串行。

## Agent 入口职责

- `.claude/hooks/*.sh`、`.codex/hooks/*.sh`、`.qoder/hooks/*.sh` 只负责定位仓库根目录并转发到共享脚本。
- agent-specific subagent 定义只保留工具面、模型、权限和简短角色差异。
- subagent handoff 字段、验证命令选择和质量目标映射不得在多个 agent 入口中复制维护；需要长期复用时应沉淀到本文件或 `AGENTS.md`。
