# Feipi Session Browser

本仓库是独立开发的本地会话浏览器，用于索引和分析 Claude Code、Codex、Qoder 等本地 agent 会话数据。

## 强约束

1. **中文优先**：面向用户输出默认简体中文；代码、命令、路径、API 名称保持英文原样。
2. **本地只读数据源**：不得修改 `~/.claude`、`~/.codex`、`~/.qoder` 原始会话数据。
3. **个人配置不入库**：不得提交 `.claude/settings.local.json`、`.mcp.json`、token、密钥、真实 session 数据或 SQLite index。
4. **先读再改**：修改前先读本文件、`docs/governance/tool-usage.md` 和相关源码/测试。
5. **保持独立项目边界**：不要重新引入 `tools/session-browser` 路径假设。

## 目录职责

| 目录 | 职责 |
|------|------|
| `src/session_browser/` | 应用源码 |
| `tests/` | 单元测试、静态 DOM/HTML 结构测试 |
| `scripts/` | 本地运行、测试、发布、harness 脚本 |
| `harness/` | Agent/自动化工作流清单 |
| `.claude/` | Claude Code 项目级共享配置和 hooks |
| `.agent/` | Agent 任务账本和执行记录 |
| `docs/` | 开发规范和项目文档 |

## 常用命令

```bash
./scripts/session-browser.sh deps
./scripts/session-browser.sh test
./scripts/session-browser.sh scan
./scripts/session-browser.sh serve
bash scripts/harness/doctor.sh
```

## 文件操作协议

- 搜索优先使用 `rg` 或 `rg --files`。
- 局部读取优先使用 `sed -n 'start,endp'`，避免无界读取大文件。
- 看 diff 先用 `git diff --stat`，再看相关文件局部 diff。
- 运行测试时保留关键失败信息，不要把超长日志原样贴给用户。

## 完成定义

1. 改动与用户目标直接对应。
2. 必要测试或静态检查已运行，并说明结果。
3. 文档、脚本、harness 与代码保持同步。
4. 没有提交个人配置、缓存、运行数据或生成物。
