# Claude Code Harness Spec

## Requirements

### Requirement: 项目级 Claude 配置

仓库 SHALL 在 `.claude/` 下提供项目 agent、commands、skills 与 settings 入口；项目说明 SHALL 使用 Claude 原生支持的 `.claude/CLAUDE.md`，顶层不保留副本。共享规则 SHALL 由 `skills/`、`harness/` 和顶层 `AGENTS.md` 维护。

#### Scenario: 加载默认 Agent

- **Given** Claude Code 从仓库根目录启动
- **When** 读取项目 settings
- **Then** 默认 agent SHALL 为仓库声明的主协调 agent
- **And** worktree 起点 SHALL 使用当前 HEAD 而不是远端默认分支猜测

### Requirement: 静态安全权限基线

项目 settings MUST 保护 `.env`、`.mcp.json`、SSH、AWS、GitHub 凭据与破坏性 shell/Git 命令；安全 deny MUST NOT 依赖 repository Session Runtime。

#### Scenario: 访问敏感路径

- **Given** 工具请求读取或修改受保护的本地凭据
- **When** Claude permissions 评估请求
- **Then** settings MUST 拒绝该操作
- **And** 拒绝 SHALL 由静态 permission 规则完成

### Requirement: 不绑定有状态 Hook matrix

项目 settings SHALL NOT 要求 SessionStart、PreToolUse、PostToolUse、PostToolUseFailure、Stop、SubagentStop、ConfigChange 或 SessionEnd 进入仓库 controller。

#### Scenario: 普通工具调用

- **Given** Claude 已在用户选择的 checkout 中工作
- **When** Read、Edit、Write 或 Bash 被调用
- **Then** 仓库 SHALL NOT 为调用创建 baseline、Registry、writer lease 或 receipt
- **And** 工具结果 SHALL 直接返回客户端

### Requirement: 原生任务完成

Claude Stop 或 SessionEnd SHALL NOT 自动运行 required tier、stage、commit 或集成 primary 分支。

#### Scenario: Claude 完成一次变更

- **Given** 当前分支包含修改
- **When** Claude 准备交接
- **Then** Agent SHALL 显式报告已运行和未运行的验证
- **And** Git mutation 只在当前任务明确要求时执行
