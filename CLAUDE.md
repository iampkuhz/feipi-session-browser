# Feipi Session Browser

独立会话浏览器项目。详细约束见 `AGENTS.md`。

## 快速入口

- 工具使用规范：`docs/governance/tool-usage.md`
- 本地测试：`./scripts/session-browser.sh test`
- 本地服务：`./scripts/session-browser.sh serve`
- Harness 检查：`bash scripts/harness/doctor.sh`

## Claude Code 注意事项

- 不修改或提交 `.claude/settings.local.json`、`.mcp.json`。
- 不读取或输出真实 session 大文件全文；需要样本时只抽取必要片段。
- 不回滚用户未提交改动。
- 结束前检查 `git status --short`，确认没有缓存、数据、密钥、index 被纳入。
