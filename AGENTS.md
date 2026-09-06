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

## 默认实现归属

- Codex 主调度时，功能、修复、重构、测试、脚本、配置、文档修改默认交给 Qoder；Codex 负责拆分、复核与验收。
- 极小任务/设计或 Qoder 不可用/权限不足/两轮返工失败时，Codex 接管并说明；禁递归派发。
- Qoder 同时最多 1 个任务，其余排队；确认结束再派发，状态不明不补开。Codex 可并行无冲突工作。
- 单目标；派发前公开 task id、读写范围、验收；集成串行。
- 首次派发/每次返工的最终回复须在正文放详情卡：标题/task id、目标/范围、验收、Qoder session/run id、权限、运行/回调/验收状态、绝对结果链接；不可只写“已派发”或藏于工具记录。模板见用法文档。
- 规则：`harness/agent-policy.manifest.yaml` 的 `qoder_delegation`；用法：`docs/development/qoder-subtasks.md`。

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
