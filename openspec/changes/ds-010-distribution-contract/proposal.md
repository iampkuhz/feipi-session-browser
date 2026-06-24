# DS-010: 发行目标、平台、升级与回滚契约

## Stage

S6 - Distribution + Operations

## Kind

PLAN - 契约冻结

## Goal

冻结正式发行包形态、目标平台/架构、安装/数据/配置/日志/缓存路径和 precedence、DB backup/migration/rollback 与版本兼容窗口、签名/notarization 策略。

## Scope

- openspec/changes/ds-010-distribution-contract/
- docs/acceptance-contracts/ds-010-distribution-contract.md
- tmp/java-migration-run/20260623-222713/47-DS-010/

## Constraints

- 不修改 production (java/**/src/main/**, src/session_browser/**, scripts/session-browser.sh)
- PLAN 任务，只产出契约文档和审计结果
- 所有新增注释使用简体中文，技术术语英文
- 不假设用户预装 JDK/Python/SQLite
- 所有发行能力有 owning task

## Non-goals

- 不实现任何发行包构建逻辑
- 不实现安装脚本或 launcher
- 不实现 DB migration 代码
- 不决定 GraalVM native-image（S6 明确不做 GraalVM）
