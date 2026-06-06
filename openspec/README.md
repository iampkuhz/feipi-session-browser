# OpenSpec

本仓库使用 OpenSpec 风格的规格驱动开发。

```text
openspec/
  config.yaml        # 工作流设置与策略配置
  specs/             # 当前真相源（git 追踪）
  schemas/           # 验证 schema（git 追踪）
  templates/         # 可复用模板（git 追踪）
  changes/           # 本地工作态（提议中的变更）
    archive/         # 目录占位
```

每个非平凡变更都从 `openspec/changes/<change-id>/` 下开始。

## 策略

- **追踪 vs 本地**：`specs/`、`schemas/`、`templates/` 是 git 追踪的，代表已批准的规范态。`changes/` 是本地工作态，默认不纳入 git 追踪。
- **受保护编辑规则**：受保护目录（`specs/`、`schemas/`、`templates/`）不能直接编辑。编辑任何受保护文件前，必须先在 `changes/` 下存在活跃的变更目录。
- **最终规格更新**：变更完成后同步到 `specs/`，再移除对应 `changes/<change-id>/`。

完整机器可读配置见 `openspec/config.yaml`。
