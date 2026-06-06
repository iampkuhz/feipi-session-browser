# Claude Code Harness Spec

## Requirements

### Requirement: Project-level Claude configuration

仓库 SHALL 在 `.claude/` 下定义项目级 commands、agents、settings 与 hooks。

### Requirement: Default main agent

仓库 MUST 提供 `qwen-main-default` 项目 agent，作为 Qwen / LiteLLM-backed Claude Code 会话的默认协调入口。

#### Scenario: Load default agent from project settings

- **Given** 开发者在仓库根目录启动 Claude Code
- **When** Claude Code 加载 `.claude/settings.json`
- **Then** 顶层 `agent` MUST 为 `qwen-main-default`

#### Scenario: Restrict main agent tools

- **Given** `.claude/agents/qwen-main-default.md` 存在
- **When** 读取 agent frontmatter
- **Then** `tools` MUST 只包含受限 `Agent(...)` 白名单、`Read`、`Edit`、`Write`、`Bash`、`Glob`、`Grep`、`TaskCreate`、`TaskUpdate`、`TaskList`、`TaskGet`
- **And** `tools` MUST NOT 包含 `LS`、`MultiEdit`、`Task`、`TodoWrite`、`BashOutput`、`KillBash`、`WebFetch`、`WebSearch`

### Requirement: Claude permissions baseline

项目级 settings MUST 保留 hooks 与安全 deny 规则，并 SHOULD 避免把历史旧工具、Web 工具、Notebook 工具作为默认 permissions allow 基线。若暂时保留 `bypassPermissions`，变更报告 MUST 明确提示风险与后续收敛建议。

#### Scenario: Keep hooks and safe denies

- **Given** `.claude/settings.json` 存在
- **When** 读取 settings
- **Then** `hooks` MUST 保留 `SessionStart`、`SubagentStart`、`PreToolUse`、`PostToolUse`、`PostToolUseFailure`、`Stop`、`SubagentStop`、`ConfigChange`
- **And** `permissions.deny` MUST 覆盖 `.env`、`.mcp.json`、`~/.ssh/**`、`~/.aws/**`、`~/.config/gh/hosts.yml` 与 destructive shell commands

#### Scenario: Avoid stale allow baseline

- **Given** `.claude/settings.json` 存在
- **When** 读取 `permissions.allow`
- **Then** `allow` MUST NOT 默认包含 `LS`、`MultiEdit`、`Task`、`TodoWrite`、`BashOutput`、`KillBash`、`WebFetch`、`WebSearch`、`NotebookEdit`
- **And** 若 `permissions.defaultMode` 仍为 `bypassPermissions`，报告 MUST 说明该模式的风险并建议后续切换为 `default`
