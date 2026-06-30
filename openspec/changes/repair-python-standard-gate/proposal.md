# Proposal: 修复 python-standard 手动质量门禁

## Problem

`python-standard` 目前以全仓 Python 基线运行，但仓库产品 Python 已退役，Java 实现是产品真相。该 target 仍引用不存在的 `src/session_browser`，并把历史 UI/Jinja 测试、中文注释标点、复杂度历史债务和网络性 `pip-audit` 问题混在一起，导致手动 full baseline 全量失败且诊断不可执行。

## Scope

- 将 `python-standard` 重新定义为手动 Python tooling baseline，覆盖 `scripts/` 与质量门、hook、harness 相关测试。
- 移除 stale `src/session_browser` 配置，不为旧 Jinja 测试恢复产品依赖。
- 校准 Ruff、Pyright、coverage、complexity、dead-code、deptry 与 Python tooling 当前职责一致。
- 修复剩余真实 Python tooling 问题，使 `python-standard` 能作为可运行的手动诊断门禁。

## Non-goals

- 不修复或恢复已迁移到 Java 的 Python 产品实现。
- 不把本变更混入 `web-010-http-route-template-asset-security-contract` 的 session-detail 浏览器门禁修复。
- 不通过新增旧 Jinja runtime 依赖来满足历史 UI 测试。
- 不提交 `.coverage*`、`coverage.xml` 或其它生成产物。

## User impact

开发者手动运行 `python3 scripts/quality/run_quality_gate.py --target python-standard --change-id <id>` 时，得到与当前仓库职责一致、可行动的 Python tooling 质量反馈。

## Validation strategy

- `python3 scripts/openspec/validate_layout.py`
- `python3 scripts/openspec/validate_schema.py`
- `python3 scripts/openspec/validate_active_change.py --change-id repair-python-standard-gate`
- `python3 scripts/harness/validate_harness_structure.py`
- `python3 scripts/quality/run_quality_gate.py --target python-standard --change-id repair-python-standard-gate`
