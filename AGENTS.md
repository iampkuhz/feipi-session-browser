# Feipi Session Browser — Agent 工程规则

本文件为短规则索引；普通定位、单文件小改不扩展。

## 首要护栏

- 默认中文回复；代码标识符、命令、路径、API 保持英文。
- 先搜索定位，再只读必要片段；不加载无关 skill 或长文档。
- 修改最小化；不纳入真实 session、密钥、token、缓存、运行数据或个人配置。
- subagent 长任务、并行探索、独立验证时主动委派；给最小 handoff、唯一 `Task id`/`agent_id`，并行写范围不重叠。
- 共用规则沉淀到 `skills/`、`harness/`；`.claude/`、`.codex/`、`.qoder/`、`.agents/` 只保留入口。

## 任务分流

- 非平凡变更（产品行为、agent/harness/质量门/hooks、目录职责、跨模块改造）先走 `openspec/changes/<id>/`。
- `openspec/specs/` 是长期真相；不要绕过 OpenSpec 大改受保护路径。

## 受保护路径

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`、`harness/`、`scripts/`、`openspec/`、`src/session_browser/`、`tests/`、`AGENTS.md`、`CLAUDE.md`。
- 修改必须目标明确、范围最小、检查 diff；不提交 `.gitignore` 忽略文件；`openspec/changes/*` 不得 `git add -f`。

## 验证原则

- required gates 全部通过才能描述完成；失败、未运行、跳过不得描述为 PASS。
- 不得新增 `pytest.skip`、`pytest.mark.skip`、`pytest.mark.skipif`、`test.skip()`、`test.describe.skip`、`test.fixme`。
- not triggered ≠ skipped；运行期间 skipped 不得算 PASS，必须补齐或报 FAIL/BLOCKED。
- 改 agent/harness/scripts/skills/openspec：优先 `bash scripts/harness/doctor.sh`。
- 改产品代码或测试：`./scripts/session-browser.sh test`。
- 改 build 配置：触发 `java-build` target。
- Stop/handoff 前运行 `scripts/quality/run_required_quality_gates.py`。
- 改 Java 源码时参考 `openspec/specs/java-code-conciseness/spec.md`。

## 提交与集成

- 修改任务使用 primary 当前 `HEAD` 的 linked worktree；Codex 用
  `scripts/harness/launch_codex_worktree.py`；不改 provider checkout。
- 完成后无需询问：按精确文件清单运行 `scripts/harness/complete_change.py`，经 Stop、commit、二次 Stop 和 `sessionctl finalize` 本地集成到启动时目标分支。
- primary/initial dirty、归因不明、detached、门禁失败或冲突时必须保留分支并报 `HANDOFF_REQUIRED`/`BLOCKED`；不得 stash、reset、force、自动 push 或把失败描述为 PASS。

## 上下文治理

- 长规则真源：`harness/agent-policy.manifest.yaml`、`harness/agent-runtime.manifest.yaml`、`skills/authoring/`。
- 跨平台共享规则放 `skills/`、`harness/`、`scripts/`；各平台配置只保留入口或链接。
