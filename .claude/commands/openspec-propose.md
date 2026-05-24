# /openspec-propose

创建新的 OpenSpec 变更。不实现代码。

Arguments: `$ARGUMENTS`

步骤：

1. 检查 `openspec/specs/` 和相关仓库文件。
2. 创建 `openspec/changes/<change-id>/proposal.md`。
3. 如果涉及 UI、架构、数据模型或导出变更，创建 `design.md`。
4. 创建 `tasks.md`，包含小型、可验证的任务。
5. 在 `openspec/changes/<change-id>/specs/` 下创建差异规格。
6. 运行 `python3 scripts/harness/validate_openspec_layout.py`。
7. 汇报创建的文件和验证结果。
