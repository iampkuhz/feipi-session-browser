# Quality Gate 派生视图

仅当任务涉及路径分类、required Gate 选择、Stop 失败或 Gate 生命周期时读取本文件。
文件名为历史导航入口；这里不保存静态 matrix。

## 唯一真源

- typed Gate、target、tier、path rule、dominance、timeout、资源与 receipt policy：
  `scripts/gates/catalog.py`。
- 确定性 classification 与冻结 plan：`scripts/gates/planner.py`。
- manual、preflight、Stop 共用 service 与唯一 CLI：`scripts/gates/cli.py`。
- Stop 薄入口与唯一 typed 管道：`scripts/harness/stop_entry.py`、
  `scripts/agent_runtime/stop/pipeline.py`。
- 模块边界、状态语义和新增/修改/删除流程：`scripts/gates/README.md`。

本文不列 target、Gate 或 path pattern。查看当前 catalog 派生结果：

```bash
python3 scripts/gates/cli.py --help
python3 scripts/gates/cli.py --tier required --dry-run
python3 scripts/gates/cli.py --tier full --dry-run
python3 scripts/gates/cli.py --target <target> --dry-run
```

## Tier 语义

- `quick`：本地快速反馈；只选择 catalog 声明的轻量 Gate。
- `required`：PR、Stop 与 handoff 的唯一基线；运行期间 skipped 即 `FAIL`/`BLOCKED`。
- `full`：发布或大迁移收口；从 catalog 选择完整 target/Gate 集合。

Stop/handoff 前使用：

```bash
python3 scripts/gates/cli.py --tier required
```

## Trigger 与 Skip

- changed files 只参与 catalog/planner 的 target 与 applicability 计算；plan 冻结后 executor 不得
  重新选择 Gate。
- `NOT_TRIGGERED` 表示本次 plan 没有选中，不等于 `SKIPPED`，也不能作为已执行 `PASS` 证据。
- 已选 Gate 未运行、缺少 fixture/env 或测试框架报告 skipped 时，必须 `FAIL`/`BLOCKED`。
- full/release 必须证明完整选中集合为零 skipped；不得用 not triggered 掩盖应运行的 Gate。

## 修改入口

新增、修改或删除 Gate 时，只维护 `scripts/gates/catalog.py` 的唯一 registration、
`scripts/checks/` 中对应 check（或对应 Gradle task）以及 contract。不要修改本文来“同步矩阵”，
不要新增 Stop/CI 专用 runner 或兼容 wrapper。完整步骤见 `scripts/gates/README.md`。
