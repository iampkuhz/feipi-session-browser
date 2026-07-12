# Scripts 维护入口

本目录承载仓库公开命令、三平台共享 Runtime、Stop 和 Gate 实现。维护者先读本页，
再按问题进入对应子目录；不要从历史路径、测试文件或文档表格推测生产入口。

## 十分钟定位路线

```text
平台 settings / CI / Gradle / 维护者命令
  -> 平台 Hook wrapper 或公开 CLI
  -> scripts/agent_runtime/hook_entry.py 或 scripts/harness/stop_entry.py
  -> identity + Registry + writer lease
  -> Stop: identity -> lock -> evidence -> reentry-recovery -> gate -> report -> finalize
  -> scripts.gates.cli.run_service
  -> catalog -> planner -> executor -> receipt + report
  -> Stop report + Registry 状态
  -> complete_change: Stop -> 精确 stage/commit -> 二次 Stop -> sessionctl finalize
```

- Hook 或 Session 生命周期问题：读 [`agent_runtime/README.md`](agent_runtime/README.md)。
- Gate 触发、执行、状态或 receipt 问题：读 [`gates/README.md`](gates/README.md)。
- 单条确定性规则问题：读 [`checks/README.md`](checks/README.md)。
- 收口、worktree 和 Registry 问题：读
  [`../docs/agent-runtime.md`](../docs/agent-runtime.md) 与
  [`../harness/agent-runtime.manifest.yaml`](../harness/agent-runtime.manifest.yaml)。

## 目录职责

| 路径 | 唯一职责 |
|---|---|
| `agent_runtime/` | 统一平台事件、身份、路径、Registry、writer lease、evidence 与 Stop 管道 |
| `gates/` | typed catalog、确定性 plan、执行、内容敏感 receipt 和结构化报告 |
| `checks/` | 不拥有进程编排的领域检查器与 Gate 叶子命令 |
| `harness/` | doctor、公开 Stop wrapper、worktree/session 生命周期与受控收口 |
| `hooks/` | 被共享 Runtime 调用的最薄仓库策略入口，不维护平台差异 |
| `openspec/` | active change 与 OpenSpec layout/schema 验证入口 |
| `release/` | release candidate、checksum 与升级/回滚 drill |
| `session-browser.sh` | 产品 launcher 与本地开发命令 |

## 公开入口 allowlist

下表是允许 settings、CI、Gradle、维护文档或人工命令稳定引用的入口。新增公开入口必须先走
OpenSpec，并同步调用方和 contract；不为历史脚本保留兼容 wrapper。

| 类别 | 公开入口 |
|---|---|
| 平台 Hook | `.claude/hooks/*.sh`、`.codex/hooks/*.sh`、`.qoder/hooks/*.sh` 中被平台配置与 `harness/agent-runtime.manifest.yaml` 登记的 wrapper |
| 产品与本地开发 | `./scripts/session-browser.sh <command>`；命令清单以 `./scripts/session-browser.sh --help` 为准 |
| Harness 健康检查 | `bash scripts/harness/doctor.sh` |
| Codex worktree | `python3 scripts/harness/launch_codex_worktree.py ...` |
| Session 生命周期 | `python3 scripts/harness/sessionctl.py <subcommand> ...` |
| 受控收口 | `python3 scripts/harness/complete_change.py --run-id ... --message ... --file ...` |
| Stop 平台委托 | `python3 scripts/harness/stop_entry.py`，仅供 Hook 与 `sessionctl` 委托，不作为手工 Gate runner |
| Gate | `python3 scripts/gates/cli.py --tier quick\|required\|full` 或 `--target <target>` |
| OpenSpec validator | `python3 scripts/openspec/validate_layout.py`、`python3 scripts/openspec/validate_schema.py`、`python3 scripts/openspec/validate_active_change.py` |
| Release | `bash scripts/release/create-release-candidate.sh`、`bash scripts/release/generate-checksums.sh`、`bash scripts/release/drill-upgrade-rollback.sh` |
| CI | `.github/workflows/*.yml` 中现有 workflow；调用命令仍须来自本 allowlist |
| Gradle | `./gradlew <task>`；可用 task 及依赖关系以 Gradle build 定义和 `./gradlew tasks` 为准 |

Stop/handoff 前唯一 required Gate 命令是：

```bash
python3 scripts/gates/cli.py --tier required
```

## 内部模块不得直跑

- 不直接运行或从 settings/CI/文档引用 `scripts/agent_runtime/**`。平台事件走 Hook wrapper，
  Runtime 诊断走 `sessionctl.py`。
- 不直接运行 `scripts/gates/catalog.py`、`planner.py`、`executor.py`、`receipt.py` 或
  `report.py`。查看 plan 使用 `scripts/gates/cli.py --dry-run`。
- `scripts/checks/**` 是 catalog 所引用的叶子规则。只有定位单个失败时才可按报告中的精确
  rerun 命令执行；它们不是另一套 required Gate runner。
- `scripts/harness/hook-common.sh` 和 Python helper 只供公开 wrapper 导入或 source。
- `tests/**`、`tmp/**` 与 artifact 路径从不构成公开命令或生产真相。

公开入口稳定不表示其内部模块可独立复用。需要变更目录职责、Hook、Stop、Gate 或公开命令时，
先创建或复用 `openspec/changes/<id>/`，再按受控收口流程提交。

## 2026-07 标准化迁移摘要

本次迁移按 Phase 1 的同一口径复核：`scripts/` 稳定源文件从 160 个降到 116 个，
其中 Python 从 150 个降到 107 个（-28.7%），总行数从 47,682 降到 36,944。
直接 import 生产脚本的测试文件在测试瘦身阶段从 43 个降到 31 个；Phase 7/8 为
baseline 同路径、资源锁、execution plan 和 receipt 新增三个长期安全 contract 后，
最终为 34 个（-20.9%）。全部测试源文件从 108 个降到 105 个。最终计数低于
25%–40% 的方向目标，是因为旧 helper 镜像测试已删除，而新增公共 Runtime/Gate
contract 与共享 `tests/support/` 直接保护安全边界，不能为数字再次删除。

按基线 inventory 的 160 个稳定源文件归档结果为：99 `DELETE`、18 `MERGE`、
16 `MOVE`、27 `KEEP`。旧 `scripts/quality/`、`scripts/claude_hooks/`、
`scripts/agent_hooks/`、`scripts/qa/` 生产路径全部下线；长期叶子规则迁入
`scripts/checks/`，共享事件与 Stop 迁入 `scripts/agent_runtime/`，执行框架迁入
`scripts/gates/`。

五个历史核心文件共 4,919 行。最终可比较的编排主干为薄 Stop 入口、Stop pipeline、
Gate CLI、planner 和 executor，共 2,580 行；typed catalog、model、receipt 与 report
作为独立数据/审计职责不计入编排主干，避免重新形成 God Script。

| 历史文件 | 最终去向 |
|---|---|
| `scripts/harness/stop_entry.py` | 保留 29 行公开薄入口，委托 typed Stop pipeline |
| `scripts/harness/stop_entry_checks/quality.py` | 删除；Stop 只调用 `scripts.gates.cli.run_service` |
| `scripts/quality/run_quality_gate.py` | 删除；拆为 catalog/planner/executor/receipt/report |
| `scripts/quality/quality_targets.py` | 删除；分类、dominance 和 tier 只存在于 typed catalog/planner |
| `scripts/quality/run_required_quality_gates.py` | 删除；required/full 共用唯一 Gate CLI/service |

固定 Java source+build 场景在正确性稳定后由 5 次顶层 Gradle invocation 降为 1 次；
同 checkout/environment/catalog/input 的内容敏感 receipt 复用实测 1.62 秒、0 次
Gradle。结构等价的八个代表场景无 Gate 差异，CPD 仍为精确单文件增量输入、两个
profile、`fullScan=false`、`dirScanUsed=false`、无 failure。
