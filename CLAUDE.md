# Feipi Session Browser

本仓库是本地 agent 会话浏览器，用于索引和分析 Claude Code、Codex、Qoder 等本地会话数据。

## 启动规则

- 本文件只提供项目入口，不承载工程细则。
- 主协调 Agent 行为由 `.claude/agents/qwen-main-default.md` 管理。
- **所有与用户的回复（思考、分析、总结、commit message 除外）统一使用中文。** Commit message 仍按项目历史风格使用英文前缀（如 `fix(codex): ...`）。
- 默认不要预读 `AGENTS.md`、`harness/`、`openspec/`、`tests/`。
- 先根据用户任务定位最小必要文件，再读取相关内容。
- 只有任务涉及非平凡开发、OpenSpec、harness、质量门或仓库规则改造时，才读取 `AGENTS.md`。

## 维护入口

- Scripts 与 Gate 的目录职责和公开命令从 `scripts/README.md` 开始定位。
- 按任务范围显式运行验证；普通提交和交接命令是
  `python3 scripts/gates/cli.py run --mode incremental`。
- `BLOCKED` 表示检查完成后发现阻断问题；`FAIL` 表示 Gate 未能完成；两者都不得描述为 `PASS`。

## Subagent 协议索引

- 长规则以 `harness/agent-policy.manifest.yaml` 的 `subagent_instance_protocol` 为准。
- Main handoff 必须包含 `Goal`、`Task id`、`Task source`、`Allowed files/directories`、`Forbidden files/directories`、`Required context files`、`Expected output`、`Validation command`、`Failure policy`，并为同一 agent 的不同实例提供唯一 `agent_id` 或等价 instance id。
- Main 只能聚合同一 `client/session_id` 的 subagent evidence；并行修改型 subagent 写范围不得重叠；subagent `FAIL`/`BLOCKED` 不得让 main 静默跳过 validation。

## 红线

- 不读取、输出或提交真实 session 大文件全文。
- 不修改 `.claude/settings.local.json`、`.mcp.json`、密钥、token 或本地个人配置，除非用户明确要求。
- 不回滚用户未提交改动。
- Gate 返回 `BLOCKED`、`FAIL` 或未完整执行时不得描述为 PASS。
