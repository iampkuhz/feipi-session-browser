# SI-010 Proposal: Scan/Index 行为清单、Schema 契约与模块拓扑

## Summary

审计 Python scan/index 代码 (~1,608 行 scanners.py + schema.py + writers.py + CLI)，
冻结所有行为、数据库契约和模块拓扑，为 S3 stage 后续 SI-020 ~ SI-120 提供明确迁移边界。

## Changes

- `openspec/changes/si-010-scan-index-contract/design.md` -- 完整审计和契约冻结
- `openspec/changes/si-010-scan-index-contract/proposal.md` -- 本文件
- `openspec/changes/si-010-scan-index-contract/tasks.md` -- S3 task 列表确认

## Scope

PLAN 任务，无 production 代码修改。

## Risk

无。仅文档产出。
