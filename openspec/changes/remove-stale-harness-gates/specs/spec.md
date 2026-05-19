# 规格增量：remove-stale-harness-gates / spec

## 需求

### 需求：默认完成门禁不得运行过期全仓扫描

默认完成门禁 MUST NOT 强制运行 `scripts/harness/check_no_unfinished_markers.py` 或 `scripts/harness/validate_task_files.py`。

#### 场景：执行默认 harness 验证

- **已知** agent 需要完成一个 OpenSpec change
- **当** agent 查看默认质量门或运行 doctor
- **则** 默认命令列表不包含 `check_no_unfinished_markers.py`
- **且** 默认命令列表不包含 `validate_task_files.py`

### 需求：过期脚本保留为可选诊断

仓库 MAY 保留 `check_no_unfinished_markers.py` 和 `validate_task_files.py` 作为手动诊断工具，但 MUST 在文档中说明它们不属于默认完成门禁。

#### 场景：需要专项清理

- **已知** 维护者想检查全仓未完成标记或旧式任务文件格式
- **当** 维护者查看质量门文档
- **则** 文档提供可选诊断命令
- **且** 文档说明它们可能命中历史文件或旧流程文件

### 需求：新 active change 不再继承过期门禁

`create_active_change.py` 写入 `.agent/active_change.json` 时，`required_gates` MUST NOT 包含这两个过期脚本。

#### 场景：创建新的 OpenSpec change

- **当** 调用 `create_active_change.py --change-id <change-id>`
- **则** 生成的 active change required gates 不包含 `check_no_unfinished_markers.py`
- **且** 不包含 `validate_task_files.py`
