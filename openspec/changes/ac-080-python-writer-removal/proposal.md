# AC-080: 删除 Python Normalized Writer 与所有权守卫

## 动机

S2C stage 第九个任务。AC-070 已证明故障注入下 canonical artifact 管线 fail closed。
现在需要删除 Python 侧的 artifact producer 代码，确保 Java 是唯一 producer。

## 范围

- `src/session_browser/normalized/artifacts.py`: 删除 writer 函数（write/persist/_write_artifact_meta）
- `src/session_browser/normalized/__init__.py`: 删除 writer exports
- `src/session_browser/index/scanners.py`: 删除 dead code（_persist 和 _should_validate/force 标志）
- `tests/`: 新增 ownership guard 测试，验证 writer API 不可达
- 清理无消费者的 dead code、旧 fixtures 和过时文档

## 约束

- 保留只读 consumer（path resolution、freshness 查找、JSON 读取）
- 不修改 forbidden scope（java/**/src/main/**、queries.py、web/**）
- 新增 ownership guard 确保任何 Python production write canonical path 都失败
- 使用 Python AST/symbol graph 枚举 writer 可达路径

## 验收标准

- Python production writer API 不存在或不可达
- Java launcher 失败时 Python 不创建 JSON/meta
- read-only consumer/index 测试通过
- ownership guard 进入 required gate
- 0 failed/errors/skipped/aborted
