# OpenSpec 变更生命周期

每个非平凡的仓库变更都遵循以下流程：

```text
提案 -> 设计 -> 任务文件 -> 串行实现 -> 验证 -> 归档
```

## 提案

创建：

```text
openspec/changes/<change-id>/proposal.md
openspec/changes/<change-id>/design.md
openspec/changes/<change-id>/tasks.md
openspec/changes/<change-id>/specs/<capability>/spec.md
```

## 实现

实现 agent 读取变更并串行执行 `tasks.md`。如果任务过大，在 `tasks/changes/<change-id>/` 下创建任务文件。

## 归档

验证通过后，将最终行为合并到 `openspec/specs/`，并将变更移至 `openspec/changes/archive/`。
