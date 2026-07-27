# Spec: Client-owned Agent Session Lifecycle

## Requirement: 客户端拥有 Session 生命周期

仓库 MUST 使用 Claude、Codex 或 Qoder 已经建立的 Session，不得为普通仓库操作维护第二套 run Registry、bootstrap、heartbeat、lease 或 completion 状态机。

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
