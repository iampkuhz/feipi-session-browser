# Gate Service

`scripts/gates/` 是 manual、preflight 与 Stop 共用的唯一 Gate service。公开 CLI 是：

```bash
python3 scripts/gates/cli.py --tier required
```

`quick`、`required`、`full`、target、Gate、path trigger、command/Gradle task、dominance、timeout、
资源、并行与 receipt metadata 的唯一声明真相是 `config/gates.yaml`。`catalog.py` 只负责加载、
schema 校验和 typed model 构造；任何 Python 或 Markdown 都不得复制完整 Gate/target 清单。

## 模块边界

| 模块 | 唯一职责 | 不负责 |
|---|---|---|
| `config/gates.yaml` | 每个普通 Gate 的唯一完整声明与 target/path/tier metadata | 执行或选择 Gate |
| `catalog.py` | 加载/schema 校验并构造 typed Gate/target/tier/path model | 维护命令表、运行命令、读取历史报告 |
| `planner.py` | 将 changed files 冻结为 classification、raw/effective target 与 applicable Gate plan | 运行时重新选择 Gate |
| `executor.py` | 冻结 command group/resource DAG 后只执行 immutable plan，落实 Gradle 聚合、bounded parallel、timeout 与跨 run 锁 | 维护另一份 Gate/target 映射 |
| `receipt.py` | 写入并校验绑定 checkout 内容、catalog 和环境的 `PASS` receipt | 缓存失败或阻断结果 |
| `report.py` | typed 状态归约、结构化 summary 与有界诊断 | 猜测未执行 Gate 的结果 |
| `cli.py` | 公开参数、统一 service、plan/execute/report/receipt 编排与退出码 | 产品业务处理 |

Stop 的 Gate 阶段只调用 `scripts.gates.cli.run_service`。不要直接运行内部模块，也不要新增
Stop 专用选择器、runner、命令表或 artifact 解析器。

## 查看当前 Gate 与计划

Gate/target 清单只从 catalog 或 CLI 派生，不在本文列出：

```bash
# 查看公开参数与 catalog 派生的 target choices
python3 scripts/gates/cli.py --help

# 查看当前工作区 required 计划，不执行子进程
python3 scripts/gates/cli.py --tier required --dry-run

# 查看 catalog 派生的完整 full 计划，不执行子进程
python3 scripts/gates/cli.py --tier full --dry-run

# 检查显式 changed-files 的 required 计划
python3 scripts/gates/cli.py \
  --tier required \
  --changed-files '["path/to/file"]' \
  --dry-run
```

`--target <target>` 用于精确诊断或维护场景；Stop/handoff 使用 `--tier required`。
显式空 changed-files 与实际 dirty 状态冲突时会 fail-closed，不能借此绕过 Gate。
changed-files 默认只供 planner 判断 target/applicability。executor 只有在 catalog 的
`changed_files_input` 明确声明支持时才传递 `QUALITY_CHANGED_FILES`；通用 Gradle 与其他 Gate
不得收到未知参数或环境变量。

dry-run 输出稳定 `planId`、`planFingerprint`、逻辑 Gate 到 group 的映射与资源 DAG；不得包含
PID、timestamp 或 run-scoped 临时路径。相同 checkout/environment 的 Gradle task 合并到一个
top-level invocation，`scanScriptSmoke` 的 `installDist` 前置也并入该 group，pytest 作为依赖后的
独立 command group。每个逻辑 Gradle Gate 从完整 plain-console task outcome 独立归约：已确认成功、
`FAILED`、`SKIPPED` 和未确认分别映射为 `EXECUTED`、`FAILED`、`FAILED`、`BLOCKED`。

只有 catalog 标记 `parallel_safe` 且资源不冲突的 group 才进入固定上限并发；冲突 group 由稳定 DAG
排序，并通过 `ResourceLockSet` 持有跨 run 的 `gradle-daemon`、`java-build-tree`、
`fixture-server` 或 `playwright-browser` 锁。timeout 会终止整个 process group，报告仍按 plan 顺序。

## Trigger、Skip 与状态

- `NOT_TRIGGERED`：路径/tier 规划没有选中该 Gate。它不等于 `SKIPPED`，也不是该 Gate 已执行的
  `PASS` 证据。
- `SKIPPED`：Gate 已被选中，但测试框架报告 skipped 或验证没有完整执行；required/full 必须归约为
  `FAIL` 或 `BLOCKED`。
- `EXECUTED`：已选 Gate 实际执行并通过。
- `REUSED`：target、changed files/baseline attribution、committed/staged/working/untracked 内容、
  catalog version、plan/command/task、Gate 输入与关键环境仍匹配可信
  `PASS` receipt，且引用的 summary 仍是完整 `PASS`。
- `FAILED` / `BLOCKED`：分别表示实际失败或无法完成/证明；都阻断 Stop 与收口。

只有选中集合全部完成且没有 skipped 才能产生 overall `PASS` 与可复用 receipt。控制台文字、
`FAIL`、`BLOCKED` 和缺少 Gate 明细都不能写成 `PASS` receipt。

summary schema 保留兼容字段，并输出 plan/checkout fingerprint、`gateStates`、command group、
duration/queue/resource wait、critical path、top-level Gradle/Python/Bash process count、receipt 原因和
精确 rerun command。成功控制台只输出单行；失败控制台只保留首因和有界诊断，完整证据位于 artifact。

## 新增、修改或删除 Gate 的唯一流程

通常只允许改三类内容：`config/gates.yaml` 的唯一 declaration、`scripts/checks/` 中对应领域检查，
以及 `tests/gates/` 或对应领域下的 contract。不得同步维护 Markdown matrix。

1. 先在 contract 中写出 trigger、plan 顺序、状态、命令和失败语义；删除 Gate 时先写无残留引用断言。
2. 新增或调整一个职责单一、可确定复现的 check；Gradle Gate 则调整对应 Gradle task contract。
3. 只在 `config/gates.yaml` 的同一 Gate 记录更新 description、target/order/pattern、tier、command 或
   Gradle task、changed-files、timeout、并行资源与 receipt policy。
4. 运行 catalog/planner/service contract，并用 `cli.py --dry-run` 检查公开 plan。
5. 运行受影响 target，再运行 `python3 scripts/gates/cli.py --tier required`。
6. 删除 Gate 时反向移除 catalog registration、对应孤立 check 与 contract，最后负向搜索旧名称和路径。

只有引入全新的 executor 类型或 report schema 时才允许在 OpenSpec 设计中扩展 `executor.py` 或
`report.py`；不能为了一个 Gate 在内部模块增加特判映射。Gate 行为变化必须同时更新 contract，
required gate 失败、未运行或 skipped 时不得描述为 `PASS`。
