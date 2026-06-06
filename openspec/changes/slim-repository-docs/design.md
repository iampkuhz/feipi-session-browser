# 设计：仓库文档瘦身

## 策略

1. 删除只记录历史变更过程的 OpenSpec change 文档，长期行为以 `openspec/specs/` 为准。
2. 保留 OpenSpec 模板、当前变更目录和必要长期规格。
3. 将 harness 文档从多篇说明手册收敛为 `harness/README.md` 和 `harness/manifest.yaml` 的当前入口。
4. 保留 `docs/page-ui-specs/`，将其作为当前页面功能要求集合。
5. 删除不直接服务当前研发的旧验收清单。
6. 对仍被脚本引用的文档，优先改脚本引用或 manifest 入口，而不是因为存在引用就保留文档。

## 验证

- `bash scripts/harness/doctor.sh`
- `python3 scripts/harness/validate_harness_structure.py`
- `python3 scripts/harness/validate_openspec_layout.py`
- `python3 scripts/quality/repo_slimming_contract_check.py`
