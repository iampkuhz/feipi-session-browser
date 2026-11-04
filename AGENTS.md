# Feipi Session Browser — Agent 工程规则

小改不扩展。

## 首要护栏

- 中文回复；标识符、命令、路径、API 保持英文。
- 先搜索定位、只读必要片段；最小修改，不加载无关文档。
- 不纳入真实 session、密钥、token、缓存、运行数据/个人配置。
- 长任务/探索/独立验证主动委派；最小 handoff、唯一 `Task id`/`agent_id`，写范围不重叠。
- 共用规则放 `skills/`、`harness/`；客户端目录仅入口。

## 任务分流

- 非平凡产品、agent、harness、gate 或跨模块变更先走 OpenSpec `openspec/changes/<id>/`；`openspec/specs/` 是长期真相。

## 原生子任务

- 直接使用当前 Agent 原生 subagents；main 负责拆分、独立复核与串行集成，不另建调度链。
- 重要实现、复杂分析和独立验证用 `gpt-6.1-sol`；轻量定位用 `gpt-6-luna`，遵守宿主模型/上下文约束。
- 派发前明确唯一身份、必要上下文、读写范围与验收；修改型任务写范围互斥，不回滚他人修改。
- 复用共享 handoff/结果协议，保持当前权限；原生能力受限时如实说明，由 main 接管或调整范围。
- 规则：`harness/agent-policy.manifest.yaml`；用法与退役边界：`docs/agent-runtime.md`。

## 受保护路径

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`、`harness/`、`scripts/`、`openspec/`、`src/session_browser/`、`scripts/tests/`、`java/tests/`、`AGENTS.md`、`.claude/CLAUDE.md`。
- 最小范围、检查 diff；不提交 ignored 文件；`openspec/changes/*` 不得 `git add -f`。

## 验证原则

- 增量 Gate 全过才完成；`BLOCKED` 为检查完成后阻断，`FAIL` 为检查未完成；均不得称 `PASS`。
- 不得新增 Python/Playwright skip、skipif、fixme API。
- 显式运行相关检查；提交/交接运行 `python3 scripts/gates/cli.py run --mode incremental`。
- 改产品代码或测试：`./scripts/session-browser.sh test`。
- 改 build 配置：触发 `java-build` target。
- 改 Java 时参考 `openspec/specs/java-code-conciseness/spec.md`。

## 提交/集成

- 只在当前 checkout/worktree 工作。
- commit、分支合并与集成均为显式操作，不由仓库生命周期自动触发。
- 禁 stash、reset、force、自动 push；不回滚用户改动。

## 上下文

- 长规则真源：`harness/agent-policy.manifest.yaml`、`skills/authoring/`。
- 共享规则放 `skills/`、`harness/`、`scripts/`；各平台配置只保留入口或链接。
