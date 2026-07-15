# Spec: Agent Session Runtime

## Requirement: 采用客户端已选择的 Checkout

Runtime MUST 采用 Agent 启动时客户端已经选择的当前 checkout，且 MUST NOT 在 Agent 运行中
创建、切换或删除第二个主 worktree。

### Scenario: 直接采用主 Checkout

- **Given** 客户端在主 checkout 启动且未提供任何 `FEIPI_*`
- **When** 首个 bootstrap 事件携带 `sessionId` 与当前 `cwd`
- **Then** Runtime MUST 为该 Session 登记 run 并采用主 checkout
- **And** 空 `changeId`、空 `taskId` 或未预列 `allowedPaths` MUST NOT 阻断冷启动

### Scenario: 采用客户端原生 Linked Worktree

- **Given** Codex、Claude、Qoder 或用户在 Agent 启动前创建了合法 linked worktree
- **When** Runtime 从该 worktree 的 `cwd` bootstrap
- **Then** Runtime MUST 采用该 checkout
- **And** Runtime MUST NOT 再创建、切换或要求固定父路径下的 worktree

### Scenario: Claude/Codex 新 Worktree 起点

- **Given** Claude 或 Codex 为新 Session 选择 linked worktree
- **When** Runtime 首次 bootstrap 该 checkout
- **Then** initial `HEAD` MUST 等于 primary checkout 当前 named branch 的精确 `HEAD`
- **And** mismatch MUST 返回 `WORKTREE_BASE_MISMATCH` 并在 mutation 前 BLOCK
- **And** Runtime MUST NOT rebase、reset、切换或删除 provider-owned checkout

### Scenario: Provider-owned Worktree 生命周期

- **Given** 当前 linked worktree 由客户端或外部 provider 创建
- **When** run 完成 cleanup、release 或 integration
- **Then** Runtime MUST 只清理指定 run 的 lease 与 evidence
- **And** Runtime MUST NOT 删除 provider-owned worktree

## Requirement: 路径无关的 Git Checkout 身份

Runtime MUST 只依据 Git 事实验证 checkout，不得把路径前缀、目录名、客户端名、`wt-*`、branch
名或创建者用作合法性或写权限依据。

### Scenario: 随机外部路径 Worktree

- **Given** linked worktree 位于 Codex App 风格的随机外部路径或 `$CODEX_HOME/worktrees`
- **And** Git metadata 证明它与目标主仓库共享同一 common-dir
- **When** Runtime 验证该 checkout
- **Then** Runtime MUST 将其识别为 `linked-worktree`
- **And** 路径不匹配任何仓库固定前缀 MUST NOT 导致 BLOCK

### Scenario: Detached HEAD

- **Given** 当前合法 checkout 处于 detached HEAD 且 branch 为空
- **When** Runtime bootstrap、授权、Stop 或 handoff
- **Then** Runtime MUST 保留 detached 事实并继续处理
- **And** branch 为空 MUST NOT 单独导致 BLOCK

### Scenario: Checkout 身份生成

- **Given** Runtime 已解析规范化 `repoKey` 与 checkout realpath
- **When** 生成 checkout identity
- **Then** `WORKTREE_ID` MUST 由 `repoKey + checkoutRoot` 的稳定摘要得到
- **And** 目录名 MUST NOT 直接成为 `WORKTREE_ID`

### Scenario: Checkout 越界

- **Given** run 已绑定一个经 Git 验证的 checkout realpath
- **When** mutation 目标越出该 checkout 或敏感路径 deny list
- **Then** Runtime MUST 阻断该 mutation
- **And** `allowedPaths` 默认 `.` MUST NOT 放宽 checkout 边界或敏感路径 deny

## Requirement: Git 外安全 Registry

Runtime MUST 将 Registry、lock 与 continuation 写入系统临时目录下按仓库隔离的安全
root，并且任何 Runtime 状态或 evidence 都 MUST NOT 写入 Git common-dir。

### Scenario: 解析 Runtime Root

- **Given** Runtime 可读取规范化 Git common-dir/主仓库身份
- **When** 解析默认存储位置
- **Then** root MUST 为 `${TMPDIR 或系统临时目录}/feipi-agent-runtime/<repo-key>/`
- **And** `repo-key` MUST 由规范化仓库身份的哈希计算
- **And** `.git/feipi-agent-runtime` MUST NOT 被创建或写入

### Scenario: Codex Workspace-write

- **Given** Codex 只允许写当前 workspace 和系统临时目录
- **When** bootstrap 创建 Registry record 或 writer lock
- **Then** 操作 MUST 无需把主仓库或 `.git` 加入额外 writable root 即成功
- **And** 实现 MUST NOT 要求关闭 sandbox 或 full access

### Scenario: 安全目录与原子更新

- **Given** Runtime 创建 root、子目录、record 或 lock
- **When** 写入或更新数据
- **Then** 目录 MUST 为当前用户独占且权限为 `0700`
- **And** Runtime MUST 防止符号链接跳转并使用原子替换
- **And** lock MUST 记录 owner、PID/start time、session/run、epoch 与时间戳

## Requirement: 唯一幂等 Bootstrap 与 Registry 权威

所有平台 MUST 调用同一个 bootstrap/session service；Registry 中与当前 Git/Session 事实一致的
记录 MUST 是 Session 身份权威，环境变量只能作为可选提示。

### Scenario: 无环境变量冷启动

- **Given** SessionStart 或首次 UserPromptSubmit 只包含 `client`、`sessionId`、`cwd`、`hookEvent`
- **When** `(repoKey, client, sessionId)` 尚无 run
- **Then** bootstrap MUST 生成唯一 `RUN_ID`
- **And** MUST 记录 HEAD、base、checkout kind/creator、branch/detached 与 initial dirty snapshot

### Scenario: Resume 与重复 Payload

- **Given** 同一 `(repoKey, client, sessionId)` 已有与当前 checkout 一致的 run
- **When** startup、resume、compact、`CwdChanged`、UserPromptSubmit 或 PreToolUse 再次触发 bootstrap
- **Then** service MUST 复用同一 run
- **And** MUST NOT 创建第二个 run 或第二个 primary checkout

### Scenario: 身份解析优先级

- **Given** Registry、Hook payload runId 与 `FEIPI_*` 环境提示同时存在
- **When** service 解析当前 Session
- **Then** MUST 按“一致 Registry → 一致 payload runId → 一致环境提示”的顺序选择
- **And** 任一候选都 MUST 与当前 `client + sessionId + cwd` 和 Git identity 一致

### Scenario: 冲突环境提示

- **Given** 环境中的 `FEIPI_RUN_ID`、`FEIPI_WORKTREE_ID` 或 `ACTIVE_CHANGE_ID` 指向其他 Session
- **When** Registry 与当前 payload/Git 事实一致
- **Then** service MUST 忽略冲突提示并写审计
- **And** 冲突提示 MUST NOT 劫持或阻断正确冷启动

## Requirement: OpenSpec Change 延迟绑定

Runtime MUST 允许 run 在 OpenSpec change 创建或选择之前存在，并提供按当前 Session 定位的
`set-change` 能力。

### Scenario: Change 尚未创建

- **Given** Session 已 bootstrap 且当前没有 active change
- **When** run record 初次写入
- **Then** `changeId` MAY 为空
- **And** 空 `changeId` MUST NOT 阻断读取、普通冷启动或 checkout 采用

### Scenario: 创建后绑定 Change

- **Given** 当前 Session 的 run 已存在
- **And** OpenSpec change 随后被创建或选择
- **When** 调用 `set-change` 并提供 change id
- **Then** Runtime MUST 通过当前 Session 找到并更新同一 run
- **And** 用户 MUST NOT 被要求手工提供 runId

## Requirement: Change Start 本地强制与显式接管

所有 mutation MUST 与同一 Session/Change 的 `ensure-session` baseline 配对；本地 launcher、
支持的 SessionStart 和 mutation guard MUST 进入共享 controller，不得依赖 LLM 记忆命令。

### Scenario: Launcher 先于 Agent 激活

- **Given** CLI launcher 已选择 checkout
- **When** launcher 准备启动 Agent 进程
- **Then** MUST 先幂等记录 repo/worktree/client/session/run、base/target、dirty snapshot、scope 与 activation evidence
- **And** 首次 mutation guard MUST 在 baseline 缺失时关闭失败

### Scenario: Codex App 能力未证明

- **Given** 仓库无法证明 Codex App host 在首次 mutation 前执行 SessionStart
- **When** adapter 报告 Start 能力
- **Then** MUST 显示 `START_NOT_ENFORCED`
- **And** MUST NOT 用 repository hook fixture 声称 App 自动保证 Start

### Scenario: Late dirty 显式接管

- **Given** checkout 在 ensure-session baseline 前已有内容
- **When** 调用唯一公开 CLI 的 `adopt-current`
- **Then** MUST 要求 base、exact manifest 与用户确认并写审计
- **And** 缺少任一证据 MUST 返回 `ADOPT_REQUIRED`
- **And** Runtime MUST NOT 创建 recovery/retry worktree

## Requirement: Checkout 级延迟 Writer Lease

bootstrap MUST NOT 立即独占 checkout；Runtime MUST 在第一次真实 mutation 前按物理 checkout
获取 writer lease，并保证同一 checkout 最多一个有效 writer。

### Scenario: 多个只读 Session

- **Given** 两个 Session 采用同一主 checkout 且都未发生 mutation
- **When** 它们执行读取或 workspace-neutral validation
- **Then** 两个 Session MUST 都能处于 `READ_ONLY_READY`
- **And** Runtime MUST NOT 为任一 Session提前独占 writer lease

### Scenario: 主 Checkout 第二写者

- **Given** 第一个 Session 已在主 checkout 的第一次 mutation 前获得有效 lease
- **When** 第二个 Session 尝试修改同一物理 checkout
- **Then** 第一个 mutation MUST 被允许
- **And** 第二个 Session 的写操作 MUST 被阻断为 `READ_ONLY_CONFLICT` 或 `BLOCKED`
- **And** 第二个 Session 的只读操作 MAY 继续

### Scenario: 不同 Worktree 并行写

- **Given** 两个 Session 分别采用同一仓库的不同合法 linked worktree
- **When** 两者各自执行第一次 mutation
- **Then** Runtime MUST 为不同 checkout key 分配独立 lease
- **And** 两个 writer MUST 能并行进入 `ISOLATED_WRITER`

### Scenario: 同一 Linked Worktree 第二写者

- **Given** 一个 Session 已持有某 linked worktree 的有效 lease
- **When** 另一个 Session 尝试修改该同一 checkout
- **Then** 第二个 writer MUST 被阻断
- **And** worktree 的客户端或路径名称 MUST NOT 改变该结果

### Scenario: Mutation 分类

- **Given** Hook 收到工具调用
- **When** 调用是 Write/Edit/MultiEdit/apply_patch 或会修改源码、配置、测试的 Bash
- **Then** Runtime MUST 在操作前获取并校验 lease
- **And** 纯读取或 workspace-neutral validation MUST NOT 获取 lease

## Requirement: Lease Fencing、恢复与继承

每个 writer lease MUST 带 epoch/fencing token；heartbeat、release 与 reclaim MUST 精确作用于指定
run/session/checkout，subagent MUST 继承主 Session 的写者身份。

### Scenario: 陈旧 Epoch 尝试写入

- **Given** 旧 Session 的 lease 已被受控回收并产生更高 epoch
- **When** 旧 Session 再次尝试 mutation
- **Then** fencing 校验 MUST 因 epoch 不匹配而阻断写入

### Scenario: 异常退出后受控 Reclaim

- **Given** owner heartbeat 过期或进程身份已失效
- **When** 新 Session 请求 reclaim
- **Then** Runtime MUST 在 mutation lock 下校验 heartbeat、PID/start time、epoch 和当前 checkout 状态
- **And** MUST 写审计并只处理目标 lease
- **And** 广域删除 Runtime 文件 MUST NOT 被用作 reclaim

### Scenario: 正常 SessionEnd

- **Given** SessionEnd 对应当前有效 lease owner
- **When** Runtime release lease
- **Then** MUST 精确释放该 run/session/checkout 的 lease
- **And** MUST NOT 影响其他 worktree 的 writer

### Scenario: Subagent 继承

- **Given** subagent 由主 Session 启动并在同一 checkout 工作
- **When** subagent 读取或 mutation
- **Then** subagent MUST 继承主 Session 的 run/worktree/lease 与 fencing token
- **And** MUST NOT 创建新的 primary writer lease

### Scenario: 初始 Dirty Checkout

- **Given** checkout 在 bootstrap 前已经 dirty
- **When** Runtime 保存 baseline 并在 controller 收口时归因变更
- **Then** 启动前变更 MUST NOT 自动归因当前 Session
- **And** 无法安全区分时 controller MUST fail closed

## Requirement: 五类平台使用薄 Adapter

Codex App、Codex CLI、Claude Code CLI、Qoder CLI 和 Qoder 客户端 adapter MUST 只规范化 payload
并调用统一 service；wrapper MUST 只转发 payload 与映射平台输出契约。

### Scenario: Codex App 与 Codex CLI

- **Given** Codex SessionStart 包含 `session_id + cwd`
- **When** adapter 处理 Local 或原生 Worktree payload
- **Then** adapter MUST 调用统一 bootstrap/adopt
- **And** SessionStart 缺失时首次 PreToolUse MUST 只做幂等兜底
- **And** MUST NOT 要求 `FEIPI_RUN_ID` 或 `--add-dir` 主仓库/`.git`

### Scenario: Codex Worktree Acquisition

- **Given** Codex CLI 没有原生 managed-worktree 参数
- **When** 用户请求隔离 worktree
- **Then** repository pre-launch launcher MUST 从稳定 primary `HEAD` snapshot 创建 checkout
- **And** CLI MUST 通过 `codex -C <checkout>` 采用它
- **And** App 原生 Worktree MUST 由用户在 UI 选择 primary 当前 starting branch
- **And** 仓库 MUST NOT 声称存在 `codex --worktree` 或可预选 App branch 的 TOML 配置

### Scenario: Claude Code CLI

- **Given** `claude` 或 `claude --worktree` 已在进程启动前确定 cwd
- **When** SessionStart 或 `CwdChanged` 到达
- **Then** adapter MUST 采用当前 checkout
- **And** `CwdChanged` MUST 只重确认身份而不得创建第二个 worktree
- **And** `CLAUDE_ENV_FILE` 中的便利变量 MUST NOT 取代 Registry 权威
- **And** repository setting `worktree.baseRef` MUST 为 `head`

## Requirement: 新 Client Worktree 使用精确 Primary HEAD

Claude Code CLI、Codex CLI 与 Codex App 的新 linked worktree MUST 使用启动前 primary checkout
当前 named branch 的已提交精确 `HEAD`，不得 fallback 到 `origin/HEAD`、远端默认分支、tracking
branch 或硬编码 `main`。

### Scenario: Primary 领先远端默认分支

- **Given** primary 位于本地 `main_java`，且 `origin/HEAD` 指向较旧 `origin/main`
- **When** 客户端 acquisition 创建 linked worktree
- **Then** initial `HEAD` MUST 等于本地 `main_java` 的 captured `HEAD`
- **And** 未 push commit MUST 保留在新 checkout 中

### Scenario: Detached 或 Snapshot Race

- **Given** primary detached，或 capture 期间 branch/HEAD 改变
- **When** acquisition 或新 run 校验起点
- **Then** 流程 MUST fail closed 并要求重试
- **And** MUST NOT 猜测默认 branch

### Scenario: Resume 不重复校验当前 Primary

- **Given** linked run 已以正确 base 登记，随后 checkout 或 primary 正常前进
- **When** 同一 Session resume 或收到重复 payload
- **Then** Runtime MUST 复用 Registry 中的 run、checkout 与 `baseCommit`
- **And** MUST NOT 把后续 commit 误判为 initial-base mismatch

### Scenario: Qoder CLI

- **Given** `qodercli` 或 `qodercli --worktree` 已确定 cwd
- **When** SessionStart 或 `CwdChanged` 到达
- **Then** adapter MUST 调用同一 bootstrap/adopt service
- **And** MUST NOT 复制 checkout 或 Registry 业务规则

### Scenario: Qoder 客户端缺少 SessionStart

- **Given** IDE/JB Hook 首次只提供 UserPromptSubmit 的 `session_id + cwd`
- **When** adapter 处理 Local 或 Worktree payload
- **Then** MUST 幂等 bootstrap 当前 checkout
- **And** PreToolUse 只能作为同一 service 的容错入口

### Scenario: 平台输出与验证状态

- **Given** 平台 Hook 对 JSON 或 exit code 有特定 contract
- **When** 统一 service 返回 allow、block 或 evidence
- **Then** wrapper MUST 仅做平台输出映射
- **And** 未在真实本地客户端执行的场景 MUST 标记 `UNVERIFIED`，不得伪造 PASS

## Requirement: 删除动态 Worktree 与两段式启动

最终实现 MUST 只有客户端选 checkout 后 bootstrap/adopt 的单一生命周期，旧动态 worktree 与
两段式启动入口、状态、schema、文档和测试 MUST 被删除而非兼容。

### Scenario: CLI Help

- **Given** 用户查看 Session Runtime CLI help
- **When** help 列出可用日常命令
- **Then** `create`、`start`、`--print-command`、`bind-session`、`recover-legacy` MUST NOT 出现
- **And** help MUST NOT 指示用户复制命令或手工注入 `FEIPI_*`

### Scenario: Hook 不 Lazy Create 或 Bind

- **Given** SessionStart 缺失且首次 prompt/tool 触发 adapter
- **When** service bootstrap 当前 checkout
- **Then** adapter MUST NOT 预创建空 sessionId run、lazy bind 或创建第二个主 worktree
- **And** `_maybe_lazy_bind_session` 等旧 authority MUST NOT 继续存在于生产路径

### Scenario: 单一文档与 Manifest

- **Given** 变更完成后扫描受跟踪文档、manifest 和 schema
- **When** 查找旧固定路径、assignment marker、`managed-worktree`、`read-only-unbound` 或
  old/new/v2/legacy 生命周期
- **Then** 被替代的生产说明和字段 MUST 已删除
- **And** MUST 只保留一份当前生命周期与一份 machine truth

## Requirement: Git 真相驱动 Status 与 On-stop

`status --compact`、`ensure-session`、`on-stop`、`resume` 与 launcher/client-exit reconciliation
MUST 实时读取 worktree HEAD、staged/unstaged/untracked、commit/ref/candidate tree、primary target
HEAD、integration 状态和当前 active Change，不得复述旧 terminal snapshot。

### Scenario: Controller 识别三类变更

- **Given** 当前 run 有已提交、未提交或 untracked 变更中的任意组合
- **When** controller 收集 Git evidence
- **Then** MUST 分别报告 committed、uncommitted 与 untracked files
- **And** MUST 报告 commits、ahead/behind、merge-base、initial dirty、checkout kind/creator 和
  target branch 状态

### Scenario: Integrated 后出现新 Mutation

- **Given** 当前 Change 已 `INTEGRATED`，且 HEAD/ref/tree 与历史 terminal seal 一致
- **When** 随后出现可归因的 staged、unstaged、deletion 或 untracked 内容并查询状态
- **Then** 历史 Change MUST 保持 `INTEGRATED` 且 commit/ref/attestation 不被回退或改写
- **And** 同一 Session MUST 建立 changeEpoch 更大的新 Change，base 等于上一 integrated commit
- **And** 新 exact manifest MUST 只包含 terminal seal 之后的 mutation
- **And** 当前状态 MUST 为 `WORKING` 或明确的 `POST_TERMINAL_MUTATION`，不得返回旧 terminal PASS

### Scenario: Terminal HEAD 或 Result 真相陈旧

- **Given** 当前 Change 的 snapshot 标记为 `INTEGRATED`
- **When** worktree HEAD、resultRef、commit tree 或 candidateTree 不一致
- **Then** reconciliation MUST 返回 `TERMINAL_BLOCKED / STALE_TERMINAL_HEAD`
- **And** MUST NOT 覆盖历史 Change 或报告 PASS

### Scenario: Primary 在 Clean Terminal 后移动

- **Given** worktree 仍 clean 且 terminal commit/ref/tree 一致
- **When** primary target HEAD 已变化
- **Then** 只有 primary 仍包含 result commit 且 target identity 一致时 MAY 保持 `INTEGRATED`
- **And** result commit 不可达或 integration 事实不成立时 MUST fail closed

### Scenario: Status 只做 Reconciliation

- **Given** 维护者或 launcher 查询当前状态
- **When** `status` 重读 Git 与 Store 真相
- **Then** 它 MUST NOT 运行 required Gate
- **And** repeated clean terminal status SHOULD 在一秒内幂等返回
- **And** 新 Change 的下一次 `on-stop` MUST 形成自己的 Attempt、fingerprint 与 receipt，不得复用上一 Change 的 PASS receipt

### Scenario: 验证期间 Checkout 发生变化

- **Given** `on-stop` 已根据当前 HEAD、index、working tree 和 untracked 内容启动 required validation
- **When** 验证期间或 receipt 落库前任一内容变化
- **Then** 内容敏感 snapshot MUST 失配并使 `on-stop` 非零退出
- **And** Runtime MUST NOT 把未验证的新状态记录为 `VALIDATED`

### Scenario: 安全 Fast-forward

- **Given** target 未前进、结果已提交且 primary checkout clean
- **When** controller 验证 base/HEAD/target 关系
- **Then** MAY 使用 ff-only 集成
- **And** MUST NOT force push、自动 push 或覆盖用户内容

### Scenario: Target 前进

- **Given** target 在 run 期间前进
- **When** controller 准备 integration
- **Then** MUST 保留已 attested commit 与 durable result ref 并返回 `COMMITTED_HANDOFF`
- **And** MUST NOT rebase、cherry-pick、创建 integration worktree 或重跑已完成的 Gate

### Scenario: Detached HEAD 收口

- **Given** run 工作在 detached HEAD
- **When** `on-stop` 需要保存结果
- **Then** MUST 形成 commit 并创建 `refs/heads/codex/result/<change-id>`
- **And** detached 状态 MUST NOT 依据路径被误判为非法 checkout

### Scenario: Commit 与 integration 解耦

- **Given** source identity、归因、exact scope、pre-commit 和 required Gate 均有效
- **When** primary dirty、target 前进或 checkout detached
- **Then** Runtime MUST 先形成本地 commit 与 durable result ref
- **And** primary 状态只影响 integration，不得阻断本地 commit

### Scenario: 必须 Handoff 的状态

- **Given** primary dirty、存在冲突、验证过期、base 非祖先或 initial dirty 无法区分
- **When** controller 判断安全性
- **Then** 已有 commit 时 MUST 返回 `COMMITTED_HANDOFF`，否则 MUST 返回明确非 PASS 状态
- **And** MUST NOT 覆盖、强制集成或删除 provider worktree

### Scenario: Run-scoped 恢复

- **Given** Stop continuation、failure fingerprint、熔断或 release/reclaim 需要更新
- **When** Runtime 写入恢复状态
- **Then** 状态 MUST 绑定指定 run/session/checkout 并写审计
- **And** Registry 路径或身份变化 MUST NOT 使其退回共享或旧状态

## Requirement: 精简且不降级的回归契约

controller MUST 使用 schema v3 的唯一权威状态 `WORKING`、`PREPARED`、`VALIDATING`、
`REPAIR_REQUIRED`、`VALIDATED`、`COMMITTED`、`COMMITTED_HANDOFF`、`INTEGRATED`、
`TERMINAL_BLOCKED`，并持久化 Session/Change/Attempt identity、stateVersion、manifestHash、
candidateTree、完整 fingerprint、commitSha 与 resultRef。环境、server、网络、timeout 与
pre-commit capability failure MUST 在同一 Change 返回明确 retryable 非 PASS 状态。

永久测试 MUST 合并重复平台与旧实现测试，同时保留 Session 身份、writer 隔离和 Git 收口的
核心黑盒保障；临时迁移/canary/performance 代码 MUST 在最终提交前删除。

### Scenario: 永久测试预算

- **Given** 变更进入最终验收
- **When** 收集相关永久测试
- **Then** 测试 SHOULD 收敛为 Session service、checkout writer lease、controller/status 三类 contract
- **And** 新永久测试文件 MUST 不超过 3 个
- **And** 相关永久测试文件总数 MUST 不增加并以净减少为目标

### Scenario: 平台参数化而非复制

- **Given** 五类 adapter 共享 bootstrap 行为
- **When** 永久测试覆盖平台差异
- **Then** MUST 使用表驱动最小 payload fixture
- **And** MUST NOT 为五个平台复制五套相同行为测试或 wrapper 测试

### Scenario: 核心保障不得因删测丢失

- **Given** 旧命令、固定路径和低价值 helper 测试已删除
- **When** 运行合并后的 targeted contract
- **Then** MUST 仍证明同 checkout 双写阻断、不同 worktree 并行、Registry 身份绑定、Git 真实
  diff 和 Stop 不伪造 PASS

### Scenario: 最终验证无跳过或告警

- **Given** targeted、required 或明确要求的 full/release regression 被触发
- **When** 测试或 gate 运行
- **Then** 结果 MUST 为 0 skipped、0 warnings 才可 PASS
- **And** required quality gates MUST 只在最终收口运行一次
- **And** 临时 fixture、canary、迁移断言、性能脚本和调试日志 MUST 已删除
