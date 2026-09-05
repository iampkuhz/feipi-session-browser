# Feipi Session Browser — Agent 工程规则

短规则索引；普通定位、单文件小改不扩展。

## 首要护栏

- 默认中文回复；代码标识符、命令、路径、API 保持英文。
- 先搜索定位再只读必要片段；最小修改；不加载无关 skill/长文档。
- 不纳入真实 session、密钥、token、缓存、运行数据或个人配置。
- 长任务/并行探索/独立验证主动委派；最小 handoff、唯一 `Task id`/`agent_id`，写范围不重叠。
- 共用规则进 `skills/`、`harness/`；各客户端目录只保留入口。

## 任务分流

- 非平凡产品、agent、harness、gate 或跨模块变更先走 OpenSpec `openspec/changes/<id>/`；`openspec/specs/` 是长期真相。

## 受保护路径

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`、`harness/`、`scripts/`、`openspec/`、`src/session_browser/`、`scripts/tests/`、`java/tests/`、`AGENTS.md`、`.claude/CLAUDE.md`。
- 目标明确、范围最小、检查 diff；不提交 ignored 文件；`openspec/changes/*` 不得 `git add -f`。

## 验证原则

- 本次增量 Gate 全过才能完成；`BLOCKED` 表示检查完成后发现阻断问题，`FAIL` 表示 Gate 未能完成；两者都不得称 `PASS`。
- 不得新增 Python/Playwright skip、skipif、fixme API。
- 按任务范围显式运行相关检查；普通提交和交接统一运行 `python3 scripts/gates/cli.py run --mode incremental`。
- 改产品代码或测试：`./scripts/session-browser.sh test`。
- 改 build 配置：触发 `java-build` target。
- 改 Java 源码时参考 `openspec/specs/java-code-conciseness/spec.md`。

## 提交与集成

- 在当前客户端选择的 checkout/worktree 中工作，不修改其他 checkout。
- commit、分支合并与集成均为显式操作，不由仓库生命周期自动触发。
- 禁止 stash、reset、force、自动 push；不回滚用户未提交改动。

## 上下文治理

- 长规则真源：`harness/agent-policy.manifest.yaml`、`skills/authoring/`。
- 跨平台共享规则放 `skills/`、`harness/`、`scripts/`；各平台配置只保留入口或链接。
