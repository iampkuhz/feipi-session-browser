# Spec: Client-owned Agent Session Lifecycle

## Requirement: 客户端拥有 Session 生命周期

仓库 MUST 使用 Claude 或 Codex 已经建立的 Session，不得为普通仓库操作维护第二套 run Registry、bootstrap、heartbeat、lease 或 completion 状态机。子任务 MUST 使用当前 Agent 原生生命周期，遵守 `native-subagent-delegation`；工程 `.qoder/` 入口及 parity 要求 MUST NOT 恢复，产品 Qoder session 支持和通用安全保护 MUST 保留。

### Scenario: Session 启动、恢复或结束

- **Given** 客户端已提供当前工作目录
- **When** Session 启动、恢复、压缩或结束
- **Then** 仓库 MUST NOT 要求 SessionStart、PreToolUse、PostToolUse、Stop 或 SessionEnd Hook 才能工作
- **And** 缺少 repository runId MUST NOT 阻断读取、编辑或显式验证

## Requirement: 客户端拥有 Checkout 选择

Runtime MUST 采用客户端已选择的当前 checkout，不得在 Agent 运行中猜测默认分支、创建第二 worktree 或切换 provider-owned checkout。

### Scenario: linked worktree 或 detached checkout

- **Given** 客户端在 linked worktree 或 detached HEAD 中启动
- **When** Agent 开始工作
- **Then** 仓库 MUST 依据当前 Git 事实工作
- **And** 路径前缀、目录名、客户端名或缺少 branch MUST NOT 单独导致 BLOCK

## Requirement: 显式 Git 生命周期

仓库 MUST NOT 自动执行 stage、commit、result-ref、fast-forward integration、rebase、cherry-pick、reset、stash、force 或 push。

### Scenario: 工作分支完成修改

- **Given** 修改位于独立工作分支
- **When** Agent 完成验证
- **Then** 修改与提交 MUST 保留在该分支
- **And** primary 分支只有在明确集成任务或用户授权后才可前进

## Requirement: 并行安全由 Git 与通用资源隔离承担

多个 Agent MAY 使用不同 checkout 并行工作；同一文件的写范围由任务 handoff 管理，Gradle、fixture server、Playwright 等共享资源由 Gate 层通用资源锁管理，不得恢复 checkout writer lease。

### Scenario: 两个独立 worktree 同时验证

- **Given** 两个 Agent 使用不同 linked worktree
- **When** 两者运行会竞争共享资源的 Gate
- **Then** Gate SHALL 按资源声明串行化冲突命令
- **And** 仓库 SHALL NOT 使用 Session writer lease 阻断普通文件编辑

## Requirement: 本地运行数据不进入仓库

临时日志、报告、缓存、真实 session、token 和个人配置 MUST 保持 ignored 且不得提交。

### Scenario: 生成验证报告

- **Given** Gate 在本地生成临时产物
- **When** Agent检查 candidate
- **Then** 产物 MUST 位于 ignored 临时目录
- **And** Git diff MUST 只包含预期源码、配置、文档或测试

### Scenario: 授权核对本机真实 session

- **Given** 当前任务授权 Agent 在本机核对相关会话
- **When** 确认行为需要原始事件或正文
- **Then** Agent MAY 定向只读必要原文，不修改或外发源记录
- **And** 输出证据 MUST 脱敏，自动化 fixture 和发行验证 MUST 使用合成样例

## Requirement: Agent 自行复核后才提交待验收

Agent MUST 从当前任务提取必验项，记录输入、预期和每项实际证据；指定样例、工程 Gate 及其他验证分别留证。修复后以相同输入复验，有可行动作时 MUST 继续。只有必验项均证实通过才可提交待验收，不以 Run 终态或 Gate 通过代替业务验证。

### Scenario: 指定样例还未定位

- **Given** 合成回归和最终 Gate 通过，指定样例尚未定位
- **When** Agent 检查是否可提交待验收
- **Then** Agent MUST 先自行追溯样例并尝试合规取证，不换样例或请用户代跑
- **And** 只有确认安全可行路径已穷尽后，才按未完成报告阻塞、已试证据和最小外部条件
