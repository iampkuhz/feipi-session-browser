# Gate 控制面维护手册

Gate 只有一个公开入口：`scripts/gates/cli.py`。Catalog 是唯一声明真源；文档不复制 20 个 Gate 的静态表。

## 操作者入口

```bash
# 查看全部 Gate 与 TargetPreset
python3 scripts/gates/cli.py list
python3 scripts/gates/cli.py list --format json

# 解释一个逻辑 Gate 或人工分组
python3 scripts/gates/cli.py explain --gate javaBuildVerification
python3 scripts/gates/cli.py explain --target agent-governance

# 只生成冻结计划，不执行；空自动输入也是合法的空计划
python3 scripts/gates/cli.py plan --mode incremental
python3 scripts/gates/cli.py plan --mode incremental --base <commit>
python3 scripts/gates/cli.py plan --mode incremental --changed-files '["scripts/gates/cli.py"]'

# 执行当前 Git staged/working/untracked 改动
python3 scripts/gates/cli.py run --mode incremental

# 人工选择必须有明确范围；无增量输入时使用 full
python3 scripts/gates/cli.py run --mode full --gate javaBuildVerification
python3 scripts/gates/cli.py run --mode full --target agent-governance

# 快速检查 Catalog、RecipeStep 适配、工具可用性和 Harness
python3 scripts/gates/cli.py health
python3 scripts/gates/cli.py health --format json

# 完整仓库验证
python3 scripts/gates/cli.py run --mode full
```

incremental 输入来自当前 Git staged/working/untracked、显式 `--base` 或显式
`--changed-files`；后两者互斥。`plan` 的 `snapshot.source` 与 `snapshot.files` 是本次选择的唯一输入证据。

`plan` 只编译 GatePlan：它展示 Trigger 因果、RecipeStep、CommandInvocation、进程数和时间目标。
空 incremental plan 以退出码 0 展示 `gates=0`。`run` 执行同一冻结计划并写 RunReceipt；空输入会写
`FAIL reason=input-empty`，因为没有 Gate 执行不能成为 PASS 证据。

`health` 编译 full GatePlan 以检查全部声明和适配，只启动 Harness doctor 一个进程，并报告真实总耗时。
它的 `planned_processes` 是声明完整性证据，`executed_processes=1` 是实际体检成本。

## 唯一流程

两张冻结图是流程和依赖的图形真源：

- [Gate 分层架构](diagrams/gate-layer-architecture/diagram.svg)
- [Gate 运行活动](diagrams/gate-run-activity/diagram.svg)

```text
ChangeSnapshot
  → TriggerMatch(file → pattern → Gate)
  → GatePlan(Gate + RecipeStep + CommandInvocation)
  → Run(StepResult → GateResult)
  → RunReceipt(schema v5)
  → canonical rerun
```

1. `capture_change_snapshot` 冻结输入来源、HEAD/base、文件和内容指纹。
2. `match_trigger` 保存每个 `file → pattern → Gate` 命中；未命中为 `NOT_TRIGGERED`，不是 PASS。
3. `compile_gate_plan` 一次性冻结 Gate、RecipeStep、真实命令、进程数和非阻断时间目标；run 不重新读取输入。
4. `orchestrate_gate_run` 串行执行完整 recipe，不 fail-fast；本阶段不做进程合并、并行、retry 或 hard timeout。
5. `classify_owner_outcome` 按 Python Check、pytest、Playwright、Gradle 类型化证据归类结果。
6. `store_run_receipt` 写入新的 `tmp/quality/runs/<run-id>/`；历史 run 不覆盖，`latest.json` 只作导航。

运行时 stderr 事件固定为 `PLAN / START / HEARTBEAT / STALL / RESULT / DONE`。长步骤每 30 秒 heartbeat；
日志 120 秒不增长只报告 STALL，不 kill。显式中断会清理受管进程组。

## 术语

| 术语 | 唯一含义 |
|---|---|
| `Gate` | 用户可见的逻辑门 |
| `TargetPreset` | 人工选择的一组 Gate；不表示耗时 |
| `RecipeStep` | Gate 内一个 owner 步骤 |
| `CommandInvocation` | 一个真实 OS 进程 |
| `GatePlan` | 输入、匹配、Gate、步骤和命令的唯一冻结计划 |
| `StepResult` / `GateResult` / `RunReceipt` | 步骤、Gate、整次运行结果 |
| `Check` | 仅指 Python 领域规则 |
| `NOT_TRIGGERED` | 选择状态，不是执行状态 |

## 阶段与文件归属

```text
catalog → planning → execution → evidence / presentation
                                  ↘ maintenance（只经公开契约审计）
checks 只实现 Python Check，由 Catalog recipe 引用
```

| 阶段 | 文件职责 |
|---|---|
| `catalog/` | contracts、recipe DSL、registry、validation、六个 domain declaration |
| `planning/` | Git 输入快照、Trigger 匹配、唯一 GatePlan |
| `execution/` | RecipeStep 适配、进程监督、owner 结果分类、运行编排 |
| `evidence/` | schema v5 immutable receipt |
| `presentation/` | human/JSON 输出与终端事件；不改业务状态 |
| `maintenance/` | 快速 health audit；编译完整计划并只运行 Harness doctor |
| `checks/` | Python Check protocol、registry 和领域实现 |

禁止逆向 import、跨阶段 helper、第二份 Gate 清单和泛化文件名。除 `__init__.py` 外，不同阶段 basename 必须唯一；
`cli.py` 不超过 250 行，核心阶段文件不超过 400 行，domain declaration 不超过 300 行。

## 状态与证据

| 状态 | 含义 |
|---|---|
| `PASS` | 所有 required RecipeStep 完整执行且通过 |
| `BLOCKED` | 验证完整执行并发现源码/规则/测试问题，`reason=verification-failed` |
| `FAIL` | 输入、依赖、运行时、中断或结果不可判定导致未完成 |

Composite 规则：任一 FAIL 则 Gate FAIL；否则任一 BLOCKED 则 Gate BLOCKED；全部 StepResult PASS 才 Gate PASS。
类型化 owner evidence 中的 warning、skipped、not-run 和 unavailable 均不得描述为 PASS；Gradle
传递图里正常无源码的非 owner task 与 Kotlin DSL housekeeping task 不进入公开 owner evidence。

## 修改步骤

1. 在 `catalog/domains/` 的唯一业务 domain 中修改 Gate、Trigger、TargetPreset、RecipeStep 或时间目标。
2. Python 规则在 `checks/<domain>/check_*.py` 实现，并只在 `checks/check_registry.py` 登记；Java/Gradle/Playwright
   继续由原生 owner 实现。
3. 运行 `list` / `explain` / `plan --format json` 确认公开名称、匹配理由和进程数。
4. 运行相关定向测试，再运行 `python3 scripts/gates/cli.py run --mode incremental`。
5. required Gate 非 PASS 时不得提交或交接为完成。
