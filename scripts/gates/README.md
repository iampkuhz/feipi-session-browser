# Gate Service

`scripts/gates/` 是 manual、preflight 与 Stop 共用的唯一 Gate service。公开 CLI 是：

```bash
python3 scripts/gates/cli.py --tier required
```

`quick`、`required`、`full`、target、Gate、path trigger、command/Gradle task、dominance、timeout、
资源与并行 metadata 的唯一声明真相是 `config/gates.yaml`。`catalog.py` 只负责加载、
schema 校验和 typed model 构造；任何 Python 或 Markdown 都不得复制完整 Gate/target 清单。

## 模块边界

| 模块 | 唯一职责 | 不负责 |
|---|---|---|
| `config/gates.yaml` | 每个普通 Gate 的唯一完整声明与 target/path/tier metadata | 执行或选择 Gate |
| `catalog.py` | 加载/schema 校验并构造 typed Gate/target/tier/path model | 维护命令表、运行命令、读取历史报告 |
| `planner.py` | 将 changed files 冻结为 classification、raw/effective target 与 applicable Gate plan | 运行时重新选择 Gate |
| `executor.py` | 冻结 ordered command group 后只执行 immutable plan，落实 Gradle 聚合、串行运行与 timeout | 维护另一份 Gate/target 映射 |
| `runtime/environment.py` | 净化并合并子进程环境 | 识别 Gate、target、session 或业务状态 |
| `runtime/process.py` | 执行 bounded subprocess、记录日志尾部并清理超时进程组 | 把退出结果归约为 Gate 五态 |
| `report.py` | typed 状态归约、结构化 summary 与有界诊断 | 猜测未执行 Gate 的结果 |
| `cli.py` | 公开参数、统一 service、plan/execute/report 编排与退出码 | 产品业务处理 |

Stop 的 Gate 阶段只调用 `scripts.gates.cli.run_service`。不要直接运行内部模块，也不要新增
Stop 专用选择器、runner、命令表或 artifact 解析器。

主调用链固定为：

```text
cli 解析输入 → planner 选择 Gate → executor 冻结 ExecutionPlan
→ executor 调度 runtime subprocess → 逻辑 Gate 状态归约 → report 写入并格式化结果
```

`runtime/` 只保存无 Gate 领域状态的环境和进程技术原语，不得导入
`cli/catalog/planner/executor/report`，也不得出现 Gate ID、target 或五态判断。

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

dry-run 输出稳定 `planId`、`planFingerprint`、逻辑 Gate 到 ordered group 的映射；不得包含
PID、timestamp 或 run-scoped 临时路径。相同 checkout/environment 的 Gradle task 合并到一个
top-level invocation，`scanScriptSmoke` 的 `installDist` 前置也并入该 group，pytest 作为依赖后的
独立 command group。每个逻辑 Gradle Gate 从完整 plain-console task outcome 独立归约：已确认成功、
`FAILED`、`SKIPPED` 和未确认分别映射为 `EXECUTED`、`FAILED`、`FAILED`、`BLOCKED`。

runner 严格按 immutable group tuple 串行执行；独立前项失败不会伪造后项 `BLOCKED`，只有
`scanScriptSmoke` 声明的 `installDist` prerequisite 未成功时才阻断其 consumer。Gradle 使用原生
daemon/build-tree 锁，fixture 使用 run-unique 临时目录和动态端口，输出限定在当前 checkout。
timeout 会终止整个 process group，报告仍按 plan 顺序。

### 共享资源归属

| 资源 | 唯一 owner | 隔离方式 |
|---|---|---|
| Gradle daemon/cache | Gradle | Gradle 原生文件锁；顶层 Gate Runner 只发起一次 Gradle |
| Gradle build tree | 当前 checkout | 每个 checkout 有自己的 `build/` 目录 |
| fixture server / port | Playwright `webServer` 与 Node starter；显式 `BASE_URL` 时为外部调用方 | identity proxy 与内部 Java child 端口都先跨 checkout 原子 claim，再由 starter 一次性消费 token；claim 只含 checkout owner，不含 run/session、lease 或 fencing |
| Playwright/browser | Playwright fixture | runtime/output 按 checkout hash 与 run 隔离；每次调用管理自己的 server/browser 生命周期 |
| 临时目录 | `executor.py` | 按 run 和 checkout hash 隔离 |
| quality artifact | `report.py` | 写入当前 checkout 下的 session/run 目录 |

不再为这些资源维护第二套 session-aware lock/fencing 控制面。若新 Gate 引入不能由
owner 自行隔离的可变共享资源，必须先增加资源 contract，再决定是否需要最小通用锁。

## Trigger、Skip 与状态

- `NOT_TRIGGERED`：路径/tier 规划没有选中该 Gate。它不等于 `SKIPPED`，也不是该 Gate 已执行的
  `PASS` 证据。
- `SKIPPED`：Gate 已被选中，但测试框架报告 skipped 或验证没有完整执行；required/full 必须归约为
  `FAIL` 或 `BLOCKED`。
- `EXECUTED`：已选 Gate 实际执行并通过。
- `FAILED` / `BLOCKED`：分别表示实际失败或无法完成/证明；都阻断 Stop 与收口。

每次调用都会执行当前 plan。只有选中集合全部完成且没有 skipped 才能产生 overall `PASS`；
控制台文字、历史结果、`FAIL`、`BLOCKED` 和缺少 Gate 明细都不能作为本次 `PASS`。

summary 输出 plan fingerprint、catalog version、`gateStates`、command group、
duration、top-level Gradle/Python/Bash process count 和
精确 rerun command。成功控制台只输出单行；失败控制台只保留首因和有界诊断，完整证据位于 artifact。

## 新增、修改或删除 Gate 的唯一流程

通常只允许改三类内容：`config/gates.yaml` 的唯一 declaration、`scripts/checks/` 中对应领域检查，
以及 `tests/gates/` 或对应领域下的 contract。不得同步维护 Markdown matrix。

1. 先在 contract 中写出 trigger、plan 顺序、状态、命令和失败语义；删除 Gate 时先写无残留引用断言。
2. 新增或调整一个职责单一、可确定复现的 check；Gradle Gate 则调整对应 Gradle task contract。
3. 只在 `config/gates.yaml` 的同一 Gate 记录更新 description、target/order/pattern、tier、command 或
   Gradle task、changed-files 与 timeout。
4. 运行 catalog/planner/service contract，并用 `cli.py --dry-run` 检查公开 plan。
5. 运行受影响 target，再运行 `python3 scripts/gates/cli.py --tier required`。
6. 删除 Gate 时反向移除 catalog registration、对应孤立 check 与 contract，最后负向搜索旧名称和路径。

只有引入全新的 executor 类型或 report schema 时才允许在 OpenSpec 设计中扩展 `executor.py` 或
`report.py`；不能为了一个 Gate 在内部模块增加特判映射。Gate 行为变化必须同时更新 contract，
required gate 失败、未运行或 skipped 时不得描述为 `PASS`。
