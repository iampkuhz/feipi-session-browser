# Gate Service

`scripts/gates/` 是本地开发与 CI 共用的唯一 Gate service。公开 CLI 是：

```bash
python3 scripts/gates/cli.py --tier required
```

`quick`、`required`、`full`、target、Gate、path trigger、typed run、dominance、timeout 和
执行参数的机器真相由 `config/gates.yaml` 根索引及其显式列出的 `config/gates/*.yaml` 共同组成。
[`config/gates/README.md`](../../config/gates/README.md) 是受 contract 保护的 44 Gate 精简目录，
不复制完整命令或 pattern；
`catalog.py` 只负责严格加载、schema 校验和 typed model 构造。

## 模块边界

| 模块 | 唯一职责 | 不负责 |
|---|---|---|
| `config/gates.yaml` | 全局 target、path rule、tier 与有序分片清单 | 保存具体 Gate 命令 |
| `config/gates/*.yaml` | 每个 Gate 的唯一完整 declaration | 复制全局 target/tier 或动态 include |
| `config/gates/README.md` | 44 Gate 的作用、实现入口、执行通道、Target、Tier 与主要触发点精简目录 | 复制完整命令或全部 pattern |
| `catalog.py` | 加载/schema 校验并构造 typed Gate/target/tier/path model | 维护命令表、运行命令、读取历史报告 |
| `planner.py` | 将 changed files 冻结为 classification、raw/effective target 与 applicable Gate plan | 运行时重新选择 Gate |
| `executor.py` | 冻结 ordered command group 后只执行 immutable plan，落实 Gradle 聚合、串行运行与 timeout | 维护另一份 Gate/target 映射 |
| `runtime/environment.py` | 净化并合并子进程环境 | 识别 Gate、target、session 或业务状态 |
| `runtime/process.py` | 执行 bounded subprocess、记录日志尾部并清理超时进程组 | 把退出结果归约为 Gate 五态 |
| `report.py` | typed 状态归约、结构化 summary 与有界诊断 | 猜测未执行 Gate 的结果 |
| `cli.py` | 公开参数、统一 service、plan/execute/report 编排与退出码 | 产品业务处理 |

不要直接运行内部模块，也不要新增第二套选择器、runner、命令表或 artifact 解析器。

主调用链固定为：

```text
cli 解析输入 → planner 选择 Gate → executor 冻结 ExecutionPlan
→ executor 调度 runtime subprocess → 逻辑 Gate 状态归约 → report 写入并格式化结果
```

`runtime/` 只保存无 Gate 领域状态的环境和进程技术原语，不得导入
`cli/catalog/planner/executor/report`，也不得出现 Gate ID、target 或五态判断。

## 从 Gate 追到实现入口

先在 `config/gates/README.md` 找 Gate，再打开该行所属的领域 YAML；不要从 executor 或文件名猜实现：

| typed `run` | 实现入口 | 继续阅读 |
|---|---|---|
| `java-rule` | Java quality-gates registry 与对应 rule | `QualityGateCli.registry()`、`QualityGateRegistry`、对应 `*Rule.java` |
| `python-check` | 共享 Python Check CLI | `scripts/checks/_registry.py`、对应唯一 `check_*.py` |
| `gradle-task` | Gradle task | 对应 `build.gradle.kts` 或 `gradle/build-logic/` task 定义 |
| `command` / `playwright` / `scan-smoke` | argv 指向的 tool 或固定 test suite | 对应公开工具、脚本或 suite contract |

实现入口直接由 typed run 派生，不另设 owner 字段。执行通道则只有 `gradle` 和 `process`：
`java-rule`、`gradle-task` 进入聚合 Gradle group，其他 run 进入 bounded process。`command` 是 run kind，
不是 owner；executor 只执行冻结后的 plan，不承载具体规则语义。

## 查看当前 Gate 与计划

完整执行清单只从 catalog 或 CLI 派生；人类概览统一位于 `config/gates/README.md`：

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

`--target <target>` 用于精确诊断或维护场景；最终验证使用 `--tier required`。
target 是 changed path 激活的可多选、有序验证场景，不是 owner、executor、tier 或唯一分类。选择顺序固定为：

```text
changed path → path rule.targets → Gate target rule（order + pattern）→ tier 过滤 → plan
```

例如 Python test 可同时激活 `acceptance-contracts` 与 `python-standard`；UI test 可同时激活
`session-detail`、`acceptance-contracts` 与 `python-standard`。
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
| fixture server / port | Playwright `webServer` 与 Node starter；显式 `BASE_URL` 时为外部调用方 | identity proxy 与 starter 协调端口 claim，由资源 owner 管理冲突和生命周期 |
| Playwright/browser | Playwright fixture | runtime/output 按 checkout hash 与 run 隔离；每次调用管理自己的 server/browser 生命周期 |
| 临时目录 | `executor.py` | 按 run 和 checkout hash 隔离 |
| Gate run summary | `report.py` | CLI 默认写到 repo-local `tmp/quality`；相对 `--out` 在 repo 下解析，显式绝对 `--out` 可选择其他根 |
| rule-scoped artifact | 产出它的 rule，例如 `CssOwnershipRule` | executor 向子进程注入执行身份根；Java 校验其 repo-local、symlink-safe 边界，rule 只写自己的子目录 |

表中资源由各自 owner 管理，不另建仓库级控制面。若新 Gate 引入不能由 owner 自行隔离的可变
共享资源，必须先增加资源 contract，再决定是否需要最小通用锁。两类质量产物边界独立：CLI 控制
Gate run summary 的输出根；executor 只向子进程注入 rule-scoped artifact 根，不能假设二者使用同一路径。

## Trigger、Skip 与状态

先区分结果语义与执行证据，不能把两层混成一套状态：

- **Gate 结果语义：** `PASS`、`FAIL`、`BLOCKED`、`SKIPPED`。`SKIPPED` 表示已选 Gate 没有完整
  执行；required/full 必须阻断，不能把它当作通过。
- **未选中语义：** `NOT_TRIGGERED` 表示路径/tier 规划没有选中该 Gate。它不等于 `SKIPPED`，
  也不是该 Gate 的 `PASS` 证据。
- **执行证据字段：** summary 的 `gateStates` 与 detail 的 `executionState` 描述是否及如何执行；其中
  `EXECUTED`、`FAILED`、`BLOCKED`、`NOT_TRIGGERED` 都只是执行证据，不是另一套 Gate 结果。
  `executionState` 还可以细分阻断原因；无论哪种值，`EXECUTED` 都不能代替 `PASS`。

每次调用都会执行当前 plan。required 只有在全部选中 Gate 实际完成并得到 `PASS` 时才能产生
overall `PASS`；控制台文字、历史结果、`FAIL`、`BLOCKED`、`SKIPPED`、`NOT_TRIGGERED` 和缺少 Gate
明细都不能作为本次通过证据。

summary 输出 plan fingerprint、catalog version、`gateStates`、command group、
duration、top-level Gradle/Python/Bash process count 和
精确 rerun command。成功控制台只输出单行；失败控制台只保留首因和有界诊断，完整证据位于 artifact。

## 一屏故障定位

| 现象 | 先确认 | 实现入口内定位 |
|---|---|---|
| `gateStates` / `executionState` 是 `NOT_TRIGGERED` | `--dry-run` 中的 path、tier、target | 修正对应领域 YAML 声明或 changed-files 输入，不伪造 Gate 结果 |
| plan 选错实现/顺序 | typed run declaration 与 ordered group | 查 `catalog.py` / `planner.py` contract，不在实现中复制 trigger |
| Java/Python/Gradle Gate 结果是 `FAIL` | rule/Check ID/task outcome 与诊断 | 回到 catalog 指向的唯一实现入口及其 contract |
| Gate 结果是 `BLOCKED` | run summary 的首因、前置结果和 rerun command | 查 required path、环境、timeout 或唯一 prerequisite |
| Gate 结果或 framework outcome 是 `SKIPPED` | framework/Gradle 的 skip 原因 | 修复未执行原因；required/full 不得将其当作 `PASS` |
| `gateStates` 是 `FAILED` / `BLOCKED`，或 `executionState` 记录失败/阻断 | 对应 command group 的执行证据 | 用它解释 `FAIL` / `BLOCKED`，不要把证据字段当成 Gate 结果 |
| timeout | 对应 command group 与 bounded log | 查 `executor.py` / `runtime/process.py`，不要在 rule 内再造 runner |

`FAIL`、`BLOCKED`、`SKIPPED` 和未运行都不是 `PASS`；`NOT_TRIGGERED` 仅表示当前 plan 没有选中，
不等于 `SKIPPED`。

## 新增、修改或删除 Gate 的唯一流程

不得在 Markdown 中复制完整 Gate 执行 matrix；`config/gates/README.md` 只保留受 contract 校验的精简目录。

1. **选择一个实现入口。** JVM/Web source rule 使用 `java-rule`；Git/OpenSpec/隐私/跨语言规则使用
   `python-check`；已有 Gradle 生命周期检查使用 `gradle-task`；工具与固定 suite 使用 `command`、
   `playwright` 或 `scan-smoke`。禁止同时保留两个实现。
2. **按 v6 strict schema 只登记一次。** 在一个 `config/gates/*.yaml` declaration 中显式写 `name`、
   `description`、`targets`（每项含 `name`、`order`、`patterns`）和单一 discriminated `run`。
   `minimum_tier`、`timeout`、`changed_files`、`network_failure` 只在偏离根 `gate_defaults` 时覆盖；
   v6 schema 未声明的兼容字段或旧式嵌套 mapping 一律拒绝。同步精简目录。
3. **先写 contract。** 覆盖真实成功、失败边界、trigger/target 与状态语义；修改实现入口时加入旧实现和
   旧 registration 的无残留断言。
4. **定向验证实现与 plan。** 运行对应 Java/Python/Gradle contract、catalog/planner/service contract，
   再用 `cli.py --dry-run` 核对公开 plan。
5. **验证 target 与 required。** 先运行受影响 target，再运行
   `python3 scripts/gates/cli.py --tier required`；任何失败、阻断或跳过都不能称为通过。
6. **负向搜索后删除。** 删除/迁移时同步移除旧实现、registration、contract 和直接 caller；旧名称与
   旧路径搜索为零后直接删除，不保留 wrapper、alias 或 adapter。

只有引入全新的 executor 类型或 report schema 时才允许在 OpenSpec 设计中扩展 `executor.py` 或
`report.py`；不能为了一个 Gate 在内部模块增加特判映射。Gate 行为变化必须同时更新 contract，
required gate 失败、未运行或 skipped 时不得描述为 `PASS`。
