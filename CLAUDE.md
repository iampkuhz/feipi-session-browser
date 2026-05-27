# Feipi Session Browser

本仓库是本地 agent 会话浏览器，用于索引和分析 Claude Code、Codex、Qoder 等本地会话数据。

## 启动规则

- 本文件只提供项目入口，不承载工程细则。
- 主协调 Agent 行为由 `.claude/agents/qwen-main-default.md` 管理。
- 默认不要预读 `AGENTS.md`、`harness/`、`openspec/`、`tests/`。
- 先根据用户任务定位最小必要文件，再读取相关内容。
- 只有任务涉及非平凡开发、OpenSpec、harness、质量门、hooks 或仓库规则改造时，才读取 `AGENTS.md`。

## 红线

- 不读取、输出或提交真实 session 大文件全文。
- 不修改 `.claude/settings.local.json`、`.mcp.json`、密钥、token 或本地个人配置，除非用户明确要求。
- 不回滚用户未提交改动。