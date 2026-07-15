# Feipi Session Browser — Agent 工程规则

短规则索引；普通定位、单文件小改不扩展。

## 首要护栏

- 默认中文回复；代码标识符、命令、路径、API 保持英文。
- 先搜索定位再只读必要片段；最小修改；不加载无关 skill/长文档。
- 不纳入真实 session、密钥、token、缓存、运行数据或个人配置。
- 长任务/并行探索/独立验证主动委派；最小 handoff、唯一 `Task id`/`agent_id`，写范围不重叠。
- 共用规则进 `skills/`、`harness/`；各客户端目录只保留入口。

## 任务分流

- 非平凡产品/agent/harness/gate/hook/跨模块变更先走 OpenSpec `openspec/changes/<id>/`；`openspec/specs/` 是长期真相。

## 受保护路径

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`、`harness/`、`scripts/`、`openspec/`、`src/session_browser/`、`tests/`、`AGENTS.md`、`CLAUDE.md`。
- 目标明确、范围最小、检查 diff；不提交 ignored 文件；`openspec/changes/*` 不得 `git add -f`。

## 验证原则

- required gates 全过才能完成；失败/未运行/skipped 不得称 PASS；not triggered ≠ skipped。
- 不得新增 Python/Playwright skip、skipif、fixme API。
- 改 agent/harness/scripts/skills/openspec：优先 `bash scripts/harness/doctor.sh`。
- 改产品代码或测试：`./scripts/session-browser.sh test`。
- 改 build 配置：触发 `java-build` target。
- Stop/handoff 前唯一门禁：`python3 scripts/gates/cli.py --tier required`。
- 改 Java 源码时参考 `openspec/specs/java-code-conciseness/spec.md`。

## 提交与集成

- 使用 primary `HEAD` 的 linked worktree；Codex 用 `scripts/harness/launch_codex_worktree.py`；不改 provider checkout。
- mutation 前须由 `change.py ensure-session` 建立 baseline；缺失/`START_NOT_ENFORCED` 时阻断。late dirty 仅可用带 base、exact manifest、用户确认的 `change.py adopt-current`。
- 无需询问：运行 `change.py on-stop`，顺序为 preflight→stage/pre-commit→一次 required Stop→commit→轻量 attestation→integration。
- 归因/禁区冲突 fail closed；能力问题报 retryable 非 PASS 并在同 Change 重试；primary dirty/前进/conflict 保留 commit/ref，报 `COMMITTED_HANDOFF`。
- 禁止 stash、reset、force、自动 push，失败不得称 PASS。

## 上下文治理

- 长规则真源：`harness/agent-policy.manifest.yaml`、`harness/agent-runtime.manifest.yaml`、`skills/authoring/`。
- 跨平台共享规则放 `skills/`、`harness/`、`scripts/`；各平台配置只保留入口或链接。
