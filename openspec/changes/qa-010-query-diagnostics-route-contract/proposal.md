# QA-010: Query、Diagnostics、Route 数据需求全量契约清单

## Stage

S4 - Query + Diagnostics + Application

## Kind

PLAN - 契约冻结

## Goal

审计 Python queries.py、diagnostics.py、metrics.py、anomalies.py、percentiles.py、routes.py、view_models.py 和 presenters 中的全部数据需求，逐项冻结 Java 查询和应用边界契约。

## Scope

- openspec/changes/qa-010-query-diagnostics-route-contract/
- docs/acceptance-contracts/qa-010-query-application.md
- tmp/java-migration-run/20260623-222713/24-QA-010/

## Constraints

- 不修改 production (java/__/src/main/**, src/session_browser/**)
- PLAN 任务，只产出契约文档和审计结果
- 所有新增注释使用简体中文，技术术语英文
