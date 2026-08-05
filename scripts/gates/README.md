# Gate Service

`scripts/gates/` 是本地开发与 CI 共用的唯一 Gate service。普通提交和交接使用：

```bash
python3 scripts/gates/cli.py --mode incremental
```

发布、周期审计或大迁移使用：

```bash
python3 scripts/gates/cli.py --mode full
```

`incremental` 与 `full` 只表示执行范围，不表示快慢或是否必须。每个 Gate 在自己的双模式
profile 中维护执行内容、`target_seconds` 和 `timeout_seconds`。
[`config/gates/README.md`](../../config/gates/README.md) 是受 contract 保护的 41 Gate 使用手册。

## 模块边界

| 模块 | 唯一职责 | 不负责 |
|---|---|---|
| `config/gates.yaml` | 注册人工 Target preset 和 Gate 分片顺序 | 配置路径触发或全局超时 |
| `config/gates/*.yaml` | 每个 Gate 的唯一五字段 declaration | 复制全局默认值或兼容旧 schema |
| `catalog.py` | 严格加载 schema 并构造 typed model | 执行命令或读历史报告 |
| `planner.py` | 将 mode、changed files 和可选 selector 冻结为 plan | 根据时效或 Target 自动猜选 Gate |
| `executor.py` | 执行选定 profile 并产生结构化证据 | 维护第二份 Gate/Trigger 映射 |
| `runtime/` | 环境净化、有界子进程和 timeout 技术原语 | 识别 Gate ID、Target 或业务状态 |
| `report.py` | 归约 Gate 终态、时效与诊断 | 扫描自然语言日志猜结果 |
| `cli.py` | 公开参数和 plan/execute/report 编排 | 产品业务处理 |

主调用链：

```text
cli 解析 GateRequest
→ planner 用 Gate.trigger 直接选 Gate
→ executor 取每个 Gate 的 incremental/full profile
→ runtime 执行有界子进程
→ report 归约 PASS/BLOCKED/FAIL
```

## 选择方式

| 调用 | 选择 Gate | profile |
|---|---|---|
| 无参数或 `--mode incremental` | changed files 直接匹配每个 Gate 的 `trigger` | incremental |
| `--mode full` | Catalog 全部 Gate | full |
| `--gate NAME --mode ...` | 精确一个 Gate，绕过 Trigger | 指定 mode |
| `--target NAME --mode ...` | 人工 preset 的全部成员，绕过 Trigger | 指定 mode |

Target 仅是人工调试/维护 preset，不参与自动选择。`docs/acceptance-cases/` 是验收用例总账，
不是 Target。`--gate` 与 `--target` 互斥。`--mode` 候选值只有 `incremental/full`，
默认 `incremental`。

```bash
# 只看当前改动的增量计划
python3 scripts/gates/cli.py --mode incremental --dry-run

# 只看全部 Gate 的 full 计划
python3 scripts/gates/cli.py --mode full --dry-run

# 人工执行某个 preset 的增量 profile
python3 scripts/gates/cli.py --target java-src --mode incremental

# 精确诊断一个 Gate
python3 scripts/gates/cli.py --gate javaCheck --mode full
```

incremental 必须拥有可信的 repo-relative changed files。显式输入格式错误、绝对路径、越界路径或
与 dirty workspace 冲突时返回 FAIL，不得自动升级为 full。full 不接受 changed files。
只有审计者明确确认“dirty workspace 仍应按空增量输入运行”时，才可同时传
`--changed-files '[]' --allow-empty-changed-files-because '<非空理由>'`；理由会写入 dry-run 和最终报告，
不能用于非空输入或 full。

## GateRequest 与 owner 输入

Planner/Executor 统一构造：

```text
GateRequest
- mode: incremental | full
- changed_files: normalized repo-relative paths（仅 incremental）
- repo_root: 当前 checkout 根（内部值）
- output_dir: 本次隔离输出目录（内部值）
```

所有 owner 收到 `QUALITY_EXECUTION_MODE=incremental|full`；incremental 另收到
`QUALITY_CHANGED_FILES` JSON 数组。owner 可以忽略 changed files，但不得改写 mode。

## 状态与退出码

| 状态 | 含义 | owner 退出码 | 处理方式 |
|---|---|---:|---|
| `PASS` | Gate 完整执行，没有发现问题 | `0` | 继续 |
| `BLOCKED` | Gate 完整执行，确认存在阻断问题 | `1` | 先修仓库，再重跑 |
| `FAIL` | Gate 自身未能完成，无法判断仓库 | `2` | 先修环境、输入或前置依赖 |

漏洞、lint 命中、测试断言失败属于 `BLOCKED`。runtime 缺失、网络不可用、timeout、
skip/no-source 属于 `FAIL`，并必须带 reason code。`NOT_TRIGGERED` 只是自动 incremental 的规划状态，
不是 Gate 终态。对外 overall 只有 `PASS/NOT_PASS`。

## 从 Gate 追到实现

先在 `config/gates/README.md` 找 Gate，再打开该行所属领域 YAML：

| typed `run.kind` | 唯一实现入口 |
|---|---|
| `java-rule` | Java quality-gates registry 与对应 rule |
| `python-check` | `scripts/checks/_registry.py` 与对应唯一 `check_*.py` |
| `gradle-task` | 对应 `build.gradle.kts` 或 build logic task |
| `command` / `playwright` / `scan-smoke` | profile 指向的 tool 或固定 suite |

## 修改 Gate 的步骤

1. 在一个 `config/gates/*.yaml` 中维护唯一 declaration。
2. Gate 顶层只写 `name`、`description`、`trigger`、`targets`、`run`。
3. `run.incremental` 和 `run.full` 分别声明执行内容、`target_seconds`和 `timeout_seconds`。
4. 用 contract 覆盖 Trigger、两个 profile 与 PASS/BLOCKED/FAIL。
5. 用 `--dry-run` 核对 plan，再运行受影响 Gate 和 `--mode incremental`。
6. 负向搜索旧 registration、caller 和术语；不保留 alias 或双 parser。
