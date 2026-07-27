# Scripts 维护入口

公开入口以 `harness/manifest.yaml` 为机器真相；本文只提供短索引。

- 产品与本地开发：`./scripts/session-browser.sh <command>`
- Harness 体检：`bash scripts/harness/doctor.sh`
- Gate：`python3 scripts/gates/cli.py --tier quick|required|full`
- 共享 checks：`python3 -m scripts.checks <check-id>`
- OpenSpec validators：`python3 scripts/openspec/validate_{layout,schema}.py`
- Active change validator：`python3 scripts/openspec/validate_active_change.py --change-id <change-id>`

目录职责：`gates/` 负责 catalog、plan、execute 与结果；`checks/` 提供领域规则；`harness/` 提供公开
脚本和验证入口；`hooks/` 只存放仍被显式调用的静态策略工具。不得把内部模块、测试、临时路径或历史
脚本当作公开入口。

客户端拥有 Session 与 checkout 生命周期，平台配置不为普通修改接线仓库状态控制器。非平凡变更先
复用 OpenSpec change。提交或交接前显式运行
`python3 scripts/gates/cli.py --tier required`；失败、未运行、warning 或 skipped 不得称为 PASS。
