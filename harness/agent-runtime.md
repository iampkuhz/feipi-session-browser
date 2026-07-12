# Agent Runtime Contract

本文件是 Claude Code、Codex、Qoder 在本仓库内复用的 agent 运行契约。`.claude/`、`.codex/`、`.qoder/`、`.agents/` 只保留工具自身需要的薄入口或链接；可复用的 skill、规则、质量目标、Stop 门禁和 handoff 约束必须放在 `skills/`、`harness/`、`scripts/harness/`、`scripts/checks/` 或 `scripts/agent_runtime/`。

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
- required Gate summary 语义：`harness/quality/deterministic-quality-gate.md`。
- Gate 模块、公开 CLI 与唯一修改流程：`scripts/gates/README.md`。
- catalog 派生阅读路线：`harness/quality/quality-gate-matrix.md`；该文档不保存静态矩阵。

## Subagent 策略

- 主 agent 应积极寻找可委派边界：长任务、并行探索、独立 QA、日志/大输出隔离、OpenSpec 规划、UI 评审、迁移分析。
- 简单单文件小改、无明确 scope、需要强串行推理、或多个 agent 会写同一文件时，不委派。
- 调用前必须提供 `Goal`、`Task id`、`Task source`、`Allowed files/directories`、`Forbidden files/directories`、`Required context files`、`Expected output`、`Validation command`、`Failure policy`。
- 可写 subagent 必须有不重叠写范围；只读 subagent 不得修改文件。

## Stop 门禁

- 三类 agent 的 Stop 入口都应调用薄 wrapper `scripts/harness/stop_entry.py`，并唯一委托 `scripts/agent_runtime/stop/pipeline.py` 的 typed 七阶段管道。
- Stop/handoff 前人工验证只运行 `python3 scripts/gates/cli.py --tier required`；不得直接运行 Gate 内部模块或拼接 check 列表。
- Stop 门禁在 hook stdin 提供 `session_id` / `agent_id` 时，必须只按 `tmp/agent_logs/<client>/<session-id>/main/` 或 `tmp/agent_logs/<client>/<session-id>/agents/<agent-id>/` 下的当前 identity evidence 判断 read-only；不得因其他并发 agent 的 dirty worktree 触发当前只读 session 的门禁。
- Stop hook 无法识别当前 session 时必须 fail-closed，继续读取 session base commit 以来的 git diff 和 untracked paths，避免未归因修改绕过 target 路由。
- `changed-files.jsonl` 用于捕获 Write/Edit/MultiEdit/NotebookEdit 和 Bash mutation evidence；Bash evidence 由 PreToolUse 快照与 PostToolUse/Failure 对比产生。
- 有 changed files 的 Stop 门禁必须先获取 shared stop-check lock；锁被占用时返回 blocked/retry，不得并发运行第二组修复或 required quality gates。
- Stop 的 Gate 阶段只能调用 `scripts.gates.cli.run_service`；target 规划、执行、receipt 与 Gate 报告均由该 service 负责。
- changed files 只能用于判断本次必须执行哪些 quality target；一旦 target 被选中，target 内部必须执行完整 required gate baseline，不得再按 changed files 裁剪 gate。
- required gate 失败时，Stop 门禁必须阻断。失败不得因为“不是当前 agent 的改动”“已有失败”“与本次改动无关”而被降级、跳过或描述为通过。

## 自动提交与本地集成

- 用户没有明确要求保留未提交状态时，named linked-worktree 的修改任务完成后必须运行 `scripts/harness/complete_change.py`，无需再次询问是否提交或合并。
- 收口命令必须接收本轮精确文件清单；实际 Git diff、staged set 与声明范围不一致，或 initial baseline 已 dirty 时必须 fail-closed，不得顺带提交其他 Session/用户内容。
- 流程固定为第一次 Stop PASS → 精确 stage/commit → commit 后第二次 Stop PASS → `sessionctl finalize`。commit 改变 HEAD/fingerprint 后不得复用第一次 receipt。
- finalize 只做本地 rebase/revalidation/`ff-only` 集成并保持 `pushed: false`；默认不得 push、创建远端 PR/MR、force、stash、reset 或删除 provider-owned checkout。
- primary dirty、detached、目标改写、验证失败/跳过或冲突时必须保留临时分支并返回 `HANDOFF_REQUIRED`/`BLOCKED`，不得描述为 PASS/INTEGRATED。
- 如果 required gate 因外部环境缺失无法运行，状态必须保持 blocked/fail，并在输出中保留可复现命令和阻断原因。


## Session Runtime

Session/bootstrap、checkout adoption、writer lease、Stop/finalize/handoff 和 provider-owned
worktree 的唯一生命周期说明见 `docs/agent-runtime.md`。机器契约由
`harness/agent-runtime.manifest.yaml` 维护；本文件不复制生命周期、Hook 矩阵或命令清单。
Claude 原生 worktree、Codex CLI/App pre-launch launcher 与 App starting branch 的准确入口也只在
该文档维护；Runtime 只对新 linked run 做 exact primary `HEAD` fail-closed 校验。

## 契约用例门禁

- 验收契约与测试的 path/target/Gate 映射只在 `scripts/gates/catalog.py` 注册，当前 plan 用
  `python3 scripts/gates/cli.py --dry-run` 查看；本文件不复制映射。
- 验收 contract checker 保持在 `scripts/checks/`，但只能由 catalog/executor 选择为生产 Gate。
- 测试代码中的 `contract_case` ID 必须能在 `docs/acceptance-contracts/features/*.md` 找到；活跃自动化用例也必须有测试绑定。

## Java 质量生命周期

- Java 源码/build 的 path rule、effective target、dominance 和 Gate 集合只由
  `scripts/gates/catalog.py` 声明，并通过 `scripts/gates/cli.py --dry-run` 派生；这里不维护副本。
- Java 注释必须通过中文近似校验，术语允许英文；术语表变更需单独列出理由。
- Javadoc Day 0：production type、public method、public constructor 必须中文 Javadoc；核心字段和 record component 必须说明业务语义。
- Java 测试 0 skipped、0 aborted、非预期 0 discovered 时失败。
- 精简质量栈：javac、Spotless、Checkstyle、DocLint、PMD、ArchUnit、JUnit、JaCoCo；禁止 Error Prone、Lombok、preview。
- artifact freshness：Gradle build cache 和 configuration cache 复用 daemon；普通任务不执行 clean；仅 checkpoint 执行完整冷构建。
- 本地有界并行：Gradle class-level fork 并行，JUnit 方法级并行关闭；建议 fork 数 `min(4, max(1, CPU/2))`。LLM 调用严格串行。

## Agent 入口职责

- `.claude/hooks/*.sh`、`.codex/hooks/*.sh`、`.qoder/hooks/*.sh` 只负责定位仓库根目录并转发到共享脚本。
- 公开命令 allowlist、内部模块禁用边界和唯一生产链路见 `scripts/README.md`。
- agent-specific subagent 定义只保留工具面、模型、权限和简短角色差异。
- subagent handoff 字段、验证命令选择和质量目标映射不得在多个 agent 入口中复制维护；需要长期复用时应沉淀到本文件或 `AGENTS.md`。
