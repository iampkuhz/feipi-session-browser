# Scripts 中文维护地图

公开入口以 `harness/manifest.yaml` 为机器真相，Gate 声明以 `config/gates.yaml` 为机器真相。本文只回答
“从哪里进入、如何找到唯一 owner”，不复制完整 Gate 清单。

## Java 维护者先看这一层

日常不要展开整个 `scripts/`。按问题逐层进入：

1. **L0 产品开发：** 只使用 `./scripts/session-browser.sh <command>`。脚本仅为
   `deps|test|quality` 保留仓库级分支，`scan|serve|stop|status|doctor|version|help`
   及其参数均透传给 Java CLI。
2. **L1 最终验证：** 只使用 `python3 scripts/gates/cli.py --tier required`；
   `./scripts/session-browser.sh quality` 是同一 required Gate 的日常入口。
3. **L2 单项诊断：** 先在 `config/gates.yaml` 查失败的 Gate，再按声明类型找到唯一 owner：
   `gradle.java_rules` 找 Java registry/rule，调用 `scripts.checks` 的 `command` 找 Python
   registry/leaf，其他 `command.argv` 直接沿 argv 找 Ruff、Pytest、Bash、Playwright 或公开工具，
   `gradle.tasks` 找对应 Gradle task。
4. **L3 基础设施维护：** 只有修改 catalog、plan、执行、状态归约、Harness、OpenSpec 或 Release
   本身时，才阅读相应内部模块。

文件浏览器中的 `__pycache__/` 和 `*.pyc` 是未跟踪运行缓存，不属于源码；应在 IDE 中隐藏。查看真实
维护面时以 `git ls-files scripts` 为准。

## 先按业务对象找目录

```text
scripts/
├── session-browser.sh        薄产品入口：三个仓库命令 + Java CLI 透传
├── checks/                   Git、OpenSpec、隐私及跨语言等共享 Python checks
│   ├── agent/                Agent 入口、权限、规则与 skill 契约
│   ├── privacy/              本地路径、真实 session 与 secret-like 内容保护
│   ├── repository/           Git、仓库结构、测试纪律与 acceptance 契约
│   ├── source/               Python/shell 注释、语言政策和产品 Python 边界
│   └── web/                  仍由 Python 所有的少量 JS/Session Detail 契约
├── gates/                    读取 catalog，选择、执行并归约 Gate
│   └── runtime/              不认识 Gate 状态的进程与环境技术原语
├── harness/                  只读体检、项目 Python 解析和 harness 结构验证
├── openspec/                 change 创建与结构/schema/active-change 验证
└── release/                  release candidate、checksum 和升级回滚演练
```

JVM 源码和已迁移的 Web resource 规则位于
`java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/`，不是
`scripts/checks/` 的 Python leaf。`harness/`、`openspec/`、`release/` 都是少量、已内聚的公开命令，
继续平铺比为单文件制造子目录更容易定位。不得创建 `misc/`、`common.py` 或 `utils.py` 来隐藏职责。

## 公开入口

- 产品与本地开发：`./scripts/session-browser.sh <command>`（唯一公开产品入口）
- Harness 体检：`bash scripts/harness/doctor.sh`
- Gate：`python3 scripts/gates/cli.py --tier quick|required|full`
- 共享 Python checks：`python3 -m scripts.checks <check-id>`
- OpenSpec validators：`python3 scripts/openspec/validate_{layout,schema}.py`
- Active change validator：
  `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`

Java rule、Python leaf 和 `scripts/gates/` 内部模块都不是额外的公开入口。单项 Python 诊断也应使用
`python3 -m scripts.checks <check-id>`，不要直接执行领域文件。

Python 开发工具不属于产品入口：依赖统一用
`UV_PROJECT_ENVIRONMENT=.local/python/venv uv sync --frozen --extra dev` 安装，单项诊断直接运行
对应工具，提交前再运行 required Gate。

## 一屏调用链

```text
required Gate:
  gates.cli
    → config/gates.yaml + catalog（唯一 Gate registration）
    → planner（按 changed files / tier 选择）
    → executor（冻结并执行命令组）
    → 根据 catalog 声明进入唯一 owner：
        gradle.java_rules             → QualityGateCli registry → Java rule
        command ... -m scripts.checks → _registry              → Python leaf
        其他 command.argv             → argv 指向的公开工具/脚本 owner
        其他 gradle.tasks             → 对应 Gradle task
    → report（严格归约状态并写 Gate run summary）

doctor:
  harness/doctor.sh
    → harness/python_env.py（选择项目 Python）
    → 只读结构、依赖与配置检查
```

## 到哪里修改

| 需求 | 唯一 owner | 同批检查 |
|---|---|---|
| 修改 JVM/Web resource 规则 | `java/tests/quality-gates/` 的 registry/rule | `config/gates.yaml`、Java contract、对应 target |
| 修改 Git/OpenSpec/隐私/跨语言规则 | `scripts/checks/<domain>/` | `_registry.py`、`config/gates.yaml`、Python contract |
| 修改 Ruff/Pytest/Bash/Playwright 等命令型 Gate | `command.argv` 指向的公开工具或脚本 | `config/gates.yaml`、工具 contract、对应 target |
| 修改普通 Gradle 检查 | 对应 `build.gradle.kts` 或 build logic task | `config/gates.yaml`、Gradle contract、对应 target |
| 修改 Gate 的 trigger、tier 或 owner registration | `config/gates.yaml` | catalog/planner/service contract 与 dry-run |
| 修改 plan、执行或状态归约 | `scripts/gates/` | 五态、timeout、Gradle outcome、report contract |
| 修改 Python 环境解析 | `scripts/harness/python_env.py` | Python resolver/lock contract |
| 修改 OpenSpec 结构 | `scripts/openspec/` | layout、schema、active-change validators |
| 修改发布流程 | `scripts/release/` | release contract、shell syntax 与 dry-run |

## 一屏故障定位

| 现象 | 先看 | 下一步 |
|---|---|---|
| Gate 未进入计划或 target 不对 | `config/gates.yaml` 与 `cli.py --dry-run` | 检查 pattern、tier、target 和 `NOT_TRIGGERED` 原因 |
| Java rule 失败 | summary 中的 rule id | 查 `QualityGateCli` registry、对应 `*Rule.java` 和 Java contract |
| Python check 失败 | 输出中的 Check ID | 查 `scripts/checks/_registry.py`、唯一 `check_*.py` 和 Python contract |
| Gradle task 失败 | catalog 的 `gradle.tasks` | 查对应 task 定义和 Gradle test/report |
| timeout 或 `BLOCKED` | artifact 中首因与 command group | 查 `scripts/gates/executor.py`、`runtime/` 和依赖前置 |
| `SKIPPED` | framework/Gradle outcome | 视为未完整执行并修复；不得改写为 `PASS` |

`FAIL`、`BLOCKED`、`SKIPPED` 和未运行都不是 `PASS`；`NOT_TRIGGERED` 仅表示当前计划没有选中，
不等于 `SKIPPED`，也不是通过证据。

移动 owner 时必须在同一批次迁移实现、catalog registration、registry/task、tests、docs 和直接 caller；
旧名称与路径负向搜索为零后直接删除，不保留 wrapper、alias 或 re-export。

客户端拥有 Session 与 checkout 生命周期，平台配置不为普通修改接线仓库状态控制器。非平凡变更先
复用 OpenSpec change。提交或交接前显式运行
`python3 scripts/gates/cli.py --tier required`；required Gate 失败、未运行、warning、skipped 或 unavailable
不得称为 PASS。
