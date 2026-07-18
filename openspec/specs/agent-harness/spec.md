# Agent Harness Spec

## Requirements

### Requirement: OpenSpec-first workflow

The repository SHALL require an OpenSpec change before non-trivial implementation work.

### Requirement: Acceptance contract mapping gate

The harness SHALL run an acceptance-contract mapping gate whenever acceptance contract docs or tests change.

#### Scenario: Contract docs change

- **Given** a file under `docs/acceptance-contracts/` changes
- **When** stop quality targets are computed
- **Then** `acceptance-contracts` SHALL be required
- **And** `scripts/checks/validate_acceptance_contracts.py` SHALL run

#### Scenario: Test markers change

- **Given** a file under `tests/` changes
- **When** stop quality targets are computed
- **Then** `acceptance-contracts` SHALL be required
- **And** orphan `contract_case` IDs SHALL fail the gate

### Requirement: Shared agent stop entrypoint

Claude Code, Codex, and Qoder stop hooks SHALL delegate to a shared harness runner instead of duplicating quality-gate logic.

#### Scenario: Shell deletion bypasses write hook evidence

- **Given** an agent deletes an acceptance contract file through a shell command
- **When** the stop hook runs
- **Then** the shared runner SHALL inspect `git status --short --untracked-files=all`
- **And** the deleted contract file SHALL still trigger the required quality target

### Requirement: Deterministic quality gate runtime

Quality gates SHALL run with a project dependency-capable Python interpreter instead of assuming PATH `python3` has the required runtime and dev dependencies.

The local harness SHALL use the same Python selection order for `deps`, `test`, doctor, and required quality gates: `SESSION_BROWSER_PYTHON` when executable, then the repository `.local/python/venv` interpreter, then the repository-approved fallback Python. Dependency declaration files and the checked-in requirements lock SHALL be treated as part of the runtime contract, and missing or inconsistent lock state SHALL fail or block doctor and required gates instead of producing a passing warning.

#### Scenario: Python gate runs from an agent hook

- **Given** an agent hook invokes the shared quality gate runner from an environment where PATH `python3` lacks project dependencies
- **When** a Python-based quality gate runs
- **Then** the gate runner SHALL prefer an explicit project Python or local project environment
- **And** `pytest` SHALL run through that Python with `-m pytest`

#### Scenario: Local test script runs without the project-local venv

- **Given** no `.local/python/venv` exists in the repository
- **And** PATH `python3` lacks dev dependencies
- **When** `./scripts/session-browser.sh test` runs
- **Then** the script SHALL prefer an explicit project Python or a Python 3 `python` before falling back to PATH `python3`

#### Scenario: Dependency lock is inconsistent

- **Given** runtime or dev dependency declarations differ from the repository-approved requirements lock
- **When** `scripts/harness/doctor.sh` or a required quality gate checks the local environment
- **Then** the check SHALL return non-zero or `BLOCKED`
- **And** the report SHALL identify the dependency declaration and lock mismatch.

#### Scenario: Fixture server cannot start

- **Given** a browser quality gate requires the HIFI fixture session
- **And** the default `BASE_URL` is not serving that fixture session
- **When** the temporary fixture server cannot start
- **Then** the fixture-dependent browser gate SHALL return `BLOCKED`
- **And** it SHALL NOT continue into a long Playwright timeout

### Requirement: Canonical two-part release version

The repository SHALL use a two-part `x.y` version as the canonical maintenance release version for local scripts, help text, and release validation.

#### Scenario: Local script reports v0.4

- **Given** `VERSION` contains `0.4`
- **When** `./scripts/session-browser.sh version` runs
- **Then** the command SHALL print `0.4`
- **And** script help SHALL present `x.y` as the default `set-version` example.

#### Scenario: Release command validates two-part version

- **Given** a release command receives `0.4`
- **When** the command validates the target version
- **Then** `0.4` SHALL be accepted as a valid release version
- **And** malformed versions SHALL fail before build, packaging, or Podman actions begin.

### Requirement: Test trigger mapping and skip semantics

The harness SHALL distinguish tests that are not triggered by path-to-target mapping from tests that are triggered but skipped at runtime.
Any selected test or required gate SHALL treat skipped outcomes as failed or blocked validation, and full or release regression SHALL prove zero skipped tests.
Any selected test, required gate, full regression, or release regression SHALL also treat warning outcomes as failed or blocked validation unless the warning cause is fixed or the trigger is removed.

#### Scenario: Change mapping does not select a gate

- **Given** a changed file does not match any pattern for a gate
- **When** required quality targets and gates are computed
- **Then** that gate SHALL be treated as not triggered
- **And** reports SHALL NOT describe it as a skipped test

#### Scenario: Selected Playwright gate reports skipped tests

- **Given** a Playwright gate is selected by path mapping, explicit command, or full regression
- **When** the Playwright command reports one or more skipped tests
- **Then** the gate SHALL fail or block instead of passing
- **And** the agent SHALL either provide the missing fixture/environment or remove the test from the triggered mapping

#### Scenario: Selected pytest gate reports skipped tests

- **Given** a pytest gate is selected by path mapping, explicit command, required baseline, or full regression
- **When** pytest reports one or more skipped outcomes
- **Then** the gate SHALL fail or block instead of passing
- **And** the report SHALL identify the outcome as skipped after trigger, not not triggered

#### Scenario: Selected pytest gate emits a warning

- **Given** `./scripts/session-browser.sh test` or a pytest quality gate is selected by explicit command, path mapping, required baseline, full regression, or release regression
- **When** pytest emits a warning summary, deprecation warning, fixture warning, or other pytest warning
- **Then** the selected gate SHALL NOT report `PASS`
- **And** the report SHALL identify the outcome as warning after trigger, not not triggered.

#### Scenario: Required doctor emits a warning

- **Given** doctor is part of required validation
- **When** doctor detects a warning condition in the Python environment, dependency lock, local-only files, or quality-gate prerequisites
- **Then** the required validation SHALL fail or block
- **And** it SHALL NOT be summarized as `PASS with warnings`.

#### Scenario: Full regression is requested

- **Given** a release or full regression has been requested
- **When** any included test would skip because required fixture or environment is missing
- **Then** the regression SHALL be reported as `FAIL` or `BLOCKED`
- **And** skipped tests SHALL NOT be counted as passing validation
- **And** the successful regression evidence SHALL show `0 skipped`

#### Scenario: New test skip API is introduced

- **Given** a change adds `pytest.skip`, `pytest.mark.skip`, `pytest.mark.skipif`, Playwright `test.skip()`, `test.describe.skip`, or `test.fixme`
- **When** the `noTestSkips` gate runs `scripts/checks/check_no_test_skips.py`
- **Then** the gate SHALL fail with the file and line number
- **And** the new skip SHALL NOT be accepted as a passing quality gate result

### Requirement: Pytest suite is warning-free for supported fixture patterns

The test suite SHALL avoid pytest fixture patterns that emit class-scoped fixture warnings under the supported pytest version and upcoming pytest 10 behavior.

#### Scenario: Session Detail page contract tests run with pytest warnings as errors

- **Given** `tests/session_detail/test_session_detail_page.py` is selected
- **When** it runs with pytest warnings promoted to errors
- **Then** collection and execution SHALL complete without class-scoped fixture warnings
- **And** existing contract-case markers SHALL remain attached to the same behavioral assertions.

## Scripts、Hook、Stop 与质量门禁标准化

### Requirement: 全量盘点与公开入口边界

Harness SHALL 在重构前盘点整个 `scripts/`、所有直接脚本测试及静态和动态调用者，并冻结有证据的公开入口 allowlist。

#### Scenario: 脚本没有静态引用

- **Given** 一个脚本没有普通 Python import 或文本路径引用
- **When** inventory 判断该脚本能否删除
- **Then** 它 SHALL 继续检查 settings、平台 Hook、CI、Gradle、Make/package、文档、动态 import、shell source/exec 和 subprocess 字符串
- **And** 单独的 `rg` 空结果 SHALL NOT 成为删除证据

#### Scenario: 冻结公开入口

- **Given** inventory 已识别三平台 Hook、维护者 CLI、worktree/change lifecycle 和 CI/Gradle 调用
- **When** 重构内部 package
- **Then** 外部确需稳定的路径 SHALL 被加入公开入口 allowlist
- **And** allowlist 外部与内部边界 SHALL 记录在 `scripts/README.md`

### Requirement: 证据驱动的脚本和测试瘦身

Harness SHALL 删除无生产价值、历史兼容、重复包装和低信息脚本及对应低价值测试，并 SHALL NOT 以机械迁移代替瘦身。

#### Scenario: 孤立脚本只被自身测试引用

- **Given** 一个非公开脚本没有生产、CI、Gradle、settings 或文档调用
- **And** 唯一调用者是与其一一对应的存在性或私有 helper 测试
- **When** 执行删除批次
- **Then** 脚本和低价值测试 SHALL 一起删除
- **And** dangling import、文档、schema、writer 或 reader SHALL 一起修复或删除

#### Scenario: 同域碎片规则可合并

- **Given** 多个检查器使用相同文件集合、依赖、运行环境和 output schema
- **When** 对检查器瘦身
- **Then** 规则 SHALL 合并为领域检查器
- **And** 进程、timeout、缓存、资源锁和报告 SHALL 继续由 Gate framework 负责
- **And** 合并结果 SHALL NOT 形成新的 God Script

#### Scenario: 瘦身未达到方向性目标

- **Given** Python 生产文件、直接测试、旧 quality runner 或核心编排行数的减幅低于变更目标
- **When** 生成最终报告
- **Then** 报告 SHALL 按领域证明保留文件的独立职责
- **And** Harness SHALL NOT 通过删除高价值 Gate、降低阈值或减少 contract 换取数字

### Requirement: 单一 Hook 到 Gate 生产链路

Claude、Codex、Qoder、manual、preflight 和 Stop SHALL 通过
`scripts/harness/hook_dispatch.py` → `scripts/agent_runtime/hook_entry.py` →
`scripts/agent_runtime/change/controller.py` 的统一 Runtime 和唯一 Gate service 执行，不得保留双轨生产 runner。

#### Scenario: 三平台处理同一事件

- **Given** Claude、Codex 和 Qoder adapter 收到语义相同的事件
- **When** adapter 规范化 payload
- **Then** 三者 SHALL 调用同一个共享 handler/service
- **And** 平台目录 SHALL 只包含 payload 和输出 contract 的差异

#### Scenario: Stop 请求执行 Gate

- **Given** controller 已收集身份、锁和 Git evidence
- **When** 进入 Gate 阶段
- **Then** controller SHALL 调用统一 Gate service
- **And** Hook adapter SHALL NOT 自行选择 Gate、解析命令、循环 subprocess 或生成另一套 Gate report

#### Scenario: 旧 runner 调用者已迁移

- **Given** settings、CI、Gradle、维护命令和文档均已调用新唯一入口
- **When** 迁移批次完成
- **Then** 旧 runner、旧 mapping、迁移 adapter 和兼容 wrapper SHALL 被删除
- **And** feature flag 或新旧双轨 SHALL NOT 进入最终交付

### Requirement: 单一 Change Controller 与公开 CLI

Change lifecycle SHALL 只由 `scripts/agent_runtime/change/controller.py` 持有业务状态机，并且只由
`scripts/harness/change.py` 提供公开 CLI。Hook adapter SHALL 只规范化 payload 与平台输出。

#### Scenario: 平台 Stop 到达 Controller

- **Given** 共享 dispatcher 收到当前 run 的 Stop payload
- **When** dispatcher 调用共享 hook entry
- **Then** hook entry SHALL 直接调用唯一 controller
- **And** identity、evidence、Gate、commit、attestation 和 integration SHALL NOT 由第二套 Stop pipeline 编排

#### Scenario: 维护者操作 Change Lifecycle

- **Given** 维护者需要 ensure-session、status、on-stop、resume、next-change、adopt-current 或 abort
- **When** 调用公开命令
- **Then** `scripts/harness/change.py` SHALL 映射 controller 的结构化状态与 exit code
- **And** 旧 Completion/Stop wrapper 或 `sessionctl` completion dispatch SHALL NOT 继续存在

### Requirement: 唯一 typed Gate catalog

所有 Gate 注册事实 SHALL 只存在于一个 typed catalog，并从它派生 target、pattern、dominance、command、tier、执行和 receipt metadata 及文档清单。

#### Scenario: 注册一个 Gate

- **Given** 维护者新增或修改 Gate
- **When** catalog 校验运行
- **Then** 记录 SHALL 包含 `name`、`targets`、`patterns`、`executorType`、`commandKey` 或 `gradleTasks`、`timeoutSeconds`、`parallelSafe`、`exclusiveResources`、`incrementalMode`、`includedBy`、`receiptPolicy`、tier 和中文说明
- **And** Gate name SHALL 唯一且依赖/includedBy 图 SHALL 无环

#### Scenario: changed files 生成 plan

- **Given** planner 收到 changed files 和 catalog version
- **When** 计算 Gate plan
- **Then** 它 SHALL 按 classification、dominance、applicability、includedBy、逻辑去重、command/task 聚合和 resource DAG 的固定顺序生成不可变 plan
- **And** executor SHALL NOT 在执行中重新选择 Gate

#### Scenario: Java source 和 build 同时命中

- **Given** raw targets 同时包含 `java-src` 与 `java-build`
- **When** planner 应用 dominance 和 includedBy
- **Then** effective plan SHALL 不重复 `javaCheck`、module boundaries、CPD/reuse 或其他同一逻辑 Gate
- **And** required Gate 覆盖 SHALL 不下降

### Requirement: 结构等价检查点

Harness SHALL 在目录和生产链路迁移后、历史正确性和性能优化前通过一次结构等价检查点。

#### Scenario: 重放代表 changed-files

- **Given** 阶段 1 保存了 Java、Hook/runtime、Python policy、session-detail 和 acceptance-contract golden 场景
- **When** 新 planner 重放相同输入
- **Then** required Gate 覆盖、quick/required/full 语义 SHALL 与批准基线等价
- **And** `NOT_TRIGGERED` SHALL NOT 记为 `SKIPPED`
- **And** 已触发的运行期 `SKIPPED` SHALL 为 `FAILED` 或 `BLOCKED`

#### Scenario: 结构等价失败

- **Given** Gate plan、Stop 状态、公开入口、adapter parity 或 CPD 对比存在未批准差异
- **When** 检查点完成判定
- **Then** 变更 SHALL 留在结构迁移阶段修复
- **And** SHALL NOT 用兼容层掩盖差异
- **And** SHALL NOT 开始历史 bug 或性能优化

#### Scenario: CPD 增量迁移

- **Given** CPD 只迁移 catalog 注册或 executor adapter
- **When** 对同一 fixture 比较迁移前后结果
- **Then** 精确输入文件列表和违规摘要 SHALL 完全等价
- **And** 算法、文件选择、阈值、违规语义和报告口径 SHALL 不变

### Requirement: 高信息中文注释硬门禁

生产 scripts 和 Hook wrapper SHALL 使用解释职责、边界、不变量及失败语义的中文说明，并 SHALL 拒绝英文主导和低信息模板注释。

#### Scenario: 核心生产模块接受审计

- **Given** 一个生产 Python module 或 Stop/Gate/锁/证据/缓存/receipt 核心函数
- **When** 中文注释 Gate 检查该文件
- **Then** module、公开 API 和安全关键说明 SHALL 以中文为主并解释职责和边界
- **And** 简单且名称明确的 private helper SHALL NOT 被迫添加模板 docstring

#### Scenario: 低信息模板出现

- **Given** 注释复述参数/返回值，包含生成式模板短语或机械中英混排
- **When** 中文注释 Gate 运行
- **Then** Gate SHALL 失败并输出文件、行号、问题类型和修改建议
- **And** 必要英文技术术语 SHALL 只通过集中 allowlist 管理

### Requirement: 公共 contract 导向的测试体系

相关测试 SHALL 按 Runtime、Gate、领域 checks 和 shared support 组织，而非按生产脚本一一镜像。

#### Scenario: 删除旧 helper 测试

- **Given** 私有 helper、旧路径或旧 wrapper 已被公共 service 取代
- **When** 测试瘦身
- **Then** 只断言源码字符串、文件存在或旧 helper 的测试 SHALL 删除
- **And** 稳定行为 SHALL 映射到公共 contract 测试

#### Scenario: 保留安全保障

- **Given** 测试文件数量减少
- **When** targeted contract 运行
- **Then** 它 SHALL 继续覆盖 catalog 完整性、changed-files golden、平台 parity、Stop 状态、worktree isolation、真实 evidence、timeout/process-group、receipt 和 CPD 等价
- **And** 已触发测试 SHALL 为 `0 skipped`、`0 warnings`

### Requirement: Changed-files 与 baseline 归因正确

Harness SHALL 只把 changed files 用于 planner/applicability 或 Gate 明确支持的输入，并以内容敏感基线区分 run 前后同路径修改。

#### Scenario: 通用 Gradle command

- **Given** 一个 Gradle Gate 不声明 changed-files 输入协议
- **When** executor 解析该 Gate 命令
- **Then** executor SHALL NOT 附加未知 `--changed-files`
- **And** `runJavaQualityGates` 与 `reuseAnalyzeIncremental` 的显式回归 SHALL 保持通过

#### Scenario: Baseline dirty 同路径再次修改

- **Given** 路径在 run 启动前已有 dirty 内容
- **When** agent 在同一路径产生新的内容或 diff
- **Then** 内容敏感快照 SHALL 将新增修改归因当前 run
- **And** 该路径 SHALL 进入 changed-files 和 Gate plan
- **And** 未触碰的 baseline dirty SHALL NOT 被归因

### Requirement: 安全的 Stop lock、worktree 隔离与熔断

Runtime SHALL 原子发布和安全回收资源 lock，阻断 run-scoped worktree 对 primary 的非受控写入，并保持 circuit OPEN 的 BLOCKED 语义。

#### Scenario: Lock owner 为 live process

- **Given** lock 含完整 owner、UID、PID/start time、inode/fencing 和有效 heartbeat
- **When** 另一个 run 尝试 reclaim
- **Then** live owner SHALL NOT 被回收
- **And** empty、corrupt、legacy、dead 或 PID reuse 状态 SHALL 按 grace period 与审计规则 fail closed 或安全回收

#### Scenario: Bash 尝试写 primary

- **Given** run 绑定 linked worktree
- **When** Bash 通过 `cp`、`mv`、`rsync`、`install`、`sed -i`、`git -C`、重定向或 symlink 尝试写 primary
- **Then** mutation SHALL 被阻断并由 primary fingerprint 补充审计
- **And** 只有持有当前 VALIDATED receipt 的受控 integration/finalize MAY 写 primary

#### Scenario: Circuit 进入 OPEN

- **Given** Stop 重入达到 circuit breaker 的 OPEN 条件
- **When** Runtime 终止自动重入
- **Then** registry、runtime report、receipt 和 integration SHALL 保持 `HANDOFF_BLOCKED` 或统一 BLOCKED
- **And** OPEN SHALL NOT 产生或复用 PASS receipt

### Requirement: 聚合且资源安全的 Gate 执行

Executor SHALL 聚合同环境 Gradle tasks，并只并行执行 catalog 声明安全且资源不冲突的 Gate。

#### Scenario: Java required plan

- **Given** required plan 包含多个相同 checkout/environment 的 Gradle Gate
- **When** executor 生成 command groups
- **Then** tasks SHALL 聚合为一次 Gradle invocation
- **And** 技术上确实不能聚合时 SHALL 最多两次并在报告解释原因
- **And** build/configuration cache SHALL 保留且 SHALL 不无故运行 `clean`

#### Scenario: Gate 竞争排他资源

- **Given** 两个 Gate 声明相同 `exclusiveResources`
- **When** bounded executor 调度 plan
- **Then** 两者 SHALL 不并行执行
- **And** 跨 run lock SHALL 至少覆盖 `gradle-daemon`、`java-build-tree`、`fixture-server` 和 `playwright-browser`
- **And** 最终输出 SHALL 按 plan 顺序稳定

### Requirement: 内容敏感且不可伪造的 PASS receipt

Manual、preflight 和 Stop SHALL 共用 receipt store，且只有真实 PASS 能生成可复用 receipt。

#### Scenario: 完全相同输入再次 Stop

- **Given** checkout committed/staged/working/untracked 内容、baseline attribution、catalog/version、resolved command/tasks、相关环境和 Gate 输入均未变化
- **When** 相同 Stop 再次运行
- **Then** 有效 PASS receipt MAY 使 Gate 标记 `REUSED`
- **And** 目标 wall time SHOULD 不超过五秒

#### Scenario: 任一关键输入变化

- **Given** receipt 绑定的任一内容、归因、catalog、command、环境或 Gate 输入发生变化
- **When** receipt store 校验复用
- **Then** receipt SHALL 失效并重新执行适用 Gate
- **And** FAIL、BLOCKED、corrupt receipt 或普通控制台文字 SHALL NOT 被当作 PASS

### Requirement: 可诊断的稳定 Gate 报告

Gate service SHALL 输出简短控制台摘要和结构化报告，且状态和重跑信息可审计。

#### Scenario: 生成结构化报告

- **Given** executor 完成或阻断一个 plan
- **When** report writer 写结果
- **Then** 报告 SHALL 包含 plan id、checkout fingerprint、target/Gate、`EXECUTED/REUSED/NOT_TRIGGERED/FAILED/BLOCKED`、command/task group、duration、queue wait、critical path、进程数、receipt 原因、resource wait 和精确 rerun 命令
- **And** 输出顺序 SHALL 与 plan 一致

#### Scenario: Gate 失败

- **Given** 一个 Gate 返回 FAILED 或 BLOCKED
- **When** CLI 打印失败摘要
- **Then** 控制台 SHALL 只显示首要原因、相关 Gate、报告路径和准确下一步
- **And** SHALL NOT 重复完整 Gradle 日志或把失败描述为 PASS

### Requirement: 分阶段验证与受控收口

变更 SHALL 按阶段 0–9 串行执行，只在结构等价阶段运行一次中型回归，并在最终清理后运行一次必要 required/full 回归和受控 finalize。

#### Scenario: 阶段内验证

- **Given** 删除、迁移、注释、测试、正确性或性能阶段完成一个批次
- **When** 执行阶段验证
- **Then** 只 SHALL 运行受影响 targeted contract
- **And** SHALL NOT 在每阶段重复仓库全量回归

#### Scenario: 最终 required 回归

- **Given** 临时内容、旧 runner、旧 mapping 和双轨实现已删除
- **When** 最终 required/full 回归运行
- **Then** 已触发测试和 Gate SHALL 为 `0 skipped`、`0 warnings` 才能 PASS
- **And** `NOT_TRIGGERED` SHALL 单独报告
- **And** required failure、BLOCKED、未运行或 skipped SHALL NOT 描述为 PASS

#### Scenario: 受控提交和集成

- **Given** 所有 required gates 真实 PASS 且本轮文件归因精确
- **When** `scripts/harness/change.py on-stop` 执行 cheap preflight、exact stage、pre-commit 稳定、candidateTree、一次 required Gate、commit、轻量 attestation 和 integration
- **Then** 只有 `INTEGRATED` 结果 SHALL 被报告为已本地集成
- **And** commit 后 attestation SHALL 验证 tree/parent/paths/clean/result ref/receipt，重 Gate进程数为 0
- **And** primary dirty 或冲突 SHALL 保留 commit/result ref 并返回 `COMMITTED_HANDOFF`
- **And** 能力失败 SHALL 在同一 Change 返回明确 retryable 非 PASS 状态，不得创建 retry worktree
- **And** 归因不明、receipt 失配或门禁失败 SHALL 如实返回非 PASS 状态
- **And** 流程 SHALL NOT stash、reset、force 或自动 push
