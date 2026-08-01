# Scripts 中文维护地图

公开入口以 `harness/manifest.yaml` 为机器真相；本文只回答“从哪里进入、到哪里修改”，不复制完整
Gate 清单。

## Java 维护者先看这一层

日常不要展开整个 `scripts/`。按问题逐层进入：

1. **L0 产品开发：** 只使用 `./scripts/session-browser.sh deps|test|scan|serve|stop`。
2. **L1 最终验证：** 只使用 `python3 scripts/gates/cli.py --tier required`；
   `session-browser.sh quality` 目前只是 Python 工具集合，不等于 required Gate。
3. **L2 单项诊断：** 根据失败输出中的 Check ID 查 `_registry.py`，再打开唯一 leaf。
4. **L3 基础设施维护：** 只有修改 Gate/Harness/OpenSpec/Release 本身时才阅读内部模块。

文件浏览器中的 `__pycache__/` 和 `*.pyc` 是未跟踪运行缓存，不属于源码；应在 IDE 中隐藏。查看真实
维护面时以 `git ls-files scripts` 为准。

## 先按业务对象找目录

```text
scripts/
├── session-browser.sh        产品运行、测试和开发命令的统一入口
├── checks/                   “具体检查什么”
│   ├── agent/                Agent 入口、权限、规则与 skill 契约
│   ├── privacy/              本地路径、真实 session 与 secret-like 内容保护
│   ├── repository/           Git、仓库结构、测试纪律与 acceptance 契约
│   ├── source/               源码语言、注释与产品 Python 边界
│   └── web/                  CSS、JavaScript、template 与 Session Detail 静态契约
├── gates/                    “选择哪些检查、如何执行、如何归约结果”
│   └── runtime/              不认识 Gate 状态的进程与环境技术原语
├── harness/                  只读体检、项目 Python 解析和 harness 结构验证
├── openspec/                 change 创建与结构/schema/active-change 验证
└── release/                  release candidate、checksum 和升级回滚演练
```

`harness/`、`openspec/`、`release/` 都是少量、已内聚的公开命令，继续平铺比为单文件制造子目录更容易
定位。不得创建 `misc/`、`common.py` 或 `utils.py` 来隐藏职责。

## 公开入口

- 产品与本地开发：`./scripts/session-browser.sh <command>`
- Harness 体检：`bash scripts/harness/doctor.sh`
- Gate：`python3 scripts/gates/cli.py --tier quick|required|full`
- 共享 checks：`python3 -m scripts.checks <check-id>`
- OpenSpec validators：`python3 scripts/openspec/validate_{layout,schema}.py`
- Active change validator：
  `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`

leaf check 和 `scripts/gates/` 内部模块不是独立入口。直接诊断 check 也应使用
`python3 -m scripts.checks <check-id>`，不要直接执行领域文件。

## 一屏调用链

```text
共享 check:
  checks.__main__
    → _registry（check ID 只在这里注册一次）
    → _framework.invoke
    → checks/<domain>/<check>.py

required Gate:
  gates.cli
    → planner（按 changed files / tier 选择）
    → executor.build_execution_plan（冻结命令组和依赖）
    → executor.execute_plan（执行并严格归约状态）
    → report（写 artifact 和有界摘要）

doctor:
  harness/doctor.sh
    → harness/python_env.py（选择项目 Python）
    → 只读结构、依赖与配置检查
```

## 到哪里修改

| 需求 | 唯一 owner | 同批检查 |
|---|---|---|
| 修改一条仓库规则 | `scripts/checks/<domain>/` | `_registry.py`、`config/gates.yaml`、对应 contract |
| 修改 Gate 的 trigger、tier 或 command | `config/gates.yaml` | catalog/planner/service contract 与 dry-run |
| 修改 plan、执行或状态归约 | `scripts/gates/` | 五态、timeout、Gradle outcome、report contract |
| 修改 Python 环境解析 | `scripts/harness/python_env.py` | Python resolver/lock contract |
| 修改 OpenSpec 结构 | `scripts/openspec/` | layout、schema、active-change validators |
| 修改发布流程 | `scripts/release/` | release contract、shell syntax 与 dry-run |

移动脚本时必须在同一批次迁移实现、registration、imports、tests、docs 和 manifest/config caller；
旧内部路径负向搜索为零后直接删除，不保留 wrapper 或 re-export。

客户端拥有 Session 与 checkout 生命周期，平台配置不为普通修改接线仓库状态控制器。非平凡变更先
复用 OpenSpec change。提交或交接前显式运行
`python3 scripts/gates/cli.py --tier required`；失败、未运行、warning、skipped 或 unavailable
不得称为 PASS。
