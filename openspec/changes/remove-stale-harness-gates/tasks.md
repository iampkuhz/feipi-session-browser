# 任务：remove-stale-harness-gates

从上到下遍历任务。不要跳过或重排。对每个任务：完成工作、标记完成（`- [x]`），并添加简短验证说明。

## 任务 1：移除默认门禁引用

- [x] 从 `AGENTS.md`、`CLAUDE.md`、change skill、`openspec-validate` 命令和 repo context 中移除两个过期门禁。

  **验证：** 使用 `rg` 检查强制流程引用。

## 任务 2：更新门禁配置和 doctor

- [x] 从 `harness/quality/gates.yaml`、`scripts/quality/doctor.py`、`create_active_change.py` 默认 `REQUIRED_GATES` 中移除两个命令。

  **验证：** 运行保留的结构验证和 doctor。

## 任务 3：保留可选诊断说明

- [x] 在 `harness/quality/gates.md` 中说明两个脚本保留为可选诊断，不再作为默认完成门禁。

  **验证：** 文档中仍能搜索到脚本名称，但只出现在可选诊断或文件存在检查中。

## 任务 4：验证并提交范围

- [x] 运行相关验证，确认暂存范围不包含 Sessions UI 半成品。

  **验证：** `git diff --cached --name-only` 只包含本次门禁调整文件。
