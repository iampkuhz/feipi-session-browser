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
