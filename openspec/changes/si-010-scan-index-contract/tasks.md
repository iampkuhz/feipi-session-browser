# SI-010 Tasks: S3 Scan/Index Task 列表确认

## 任务顺序 (来自 stages/S3/README.md)

| Order | Task ID | Kind | 说明 |
|-------|---------|------|------|
| 11 | SI-010 | PLAN | Scan/Index 行为清单、Schema 契约与模块拓扑 (本任务) |
| 12 | SI-020 | IMPLEMENT | SQLite Schema、版本与可回滚 Migration |
| 13 | SI-030 | IMPLEMENT | SQLite Connection、PRAGMA、事务与单 Writer 基础设施 |
| 14 | SI-040 | IMPLEMENT | Normalized Artifact 到 Index Row 映射与不变量 |
| 15 | SI-050 | IMPLEMENT | Java Full Scan Engine |
| 16 | SI-060 | IMPLEMENT | Java Incremental Scan 状态机 |
| 17 | SI-070 | IMPLEMENT | 删除、重命名、孤儿与 Repair 状态机 |
| 18 | SI-080 | IMPLEMENT | Tiered/Background Scan、锁、取消与 Shutdown |
| 19 | SI-085 | OPTIMIZE | Scan/Index 专题精简与事务性能优化 |
| 20 | SI-090 | GATE | Scan/Index 故障、并发、性能只读门禁 |
| 21 | SI-100 | IMPLEMENT | Java scan CLI、Shell 路由与用户行为 Cutover |
| 22 | SI-110 | IMPLEMENT | 退休 Python Scan 与 SQLite 写路径 |
| 23 | SI-120 | CLOSEOUT | S3 Scan/Index 所有权与 Stage 收口 |

## 本 task 产出

1. 行为枚举: full/incremental/startup/hot/warm/delete/rename/repair/lock/cancel
2. Schema 冻结: sessions/scan_log/index_metadata/session_artifacts
3. 模块拓扑: application/scan-engine/index-sqlite
4. Symbol 归属: 每个 Python symbol 到具体 SI task 或 DO_NOT_MIGRATE
5. 状态机冻结: scan_log/session candidate/artifact validation/scan lock/tier dispatch

## Schema 契约 owner

| Schema | 实现 task | 测试 owner |
|--------|----------|-----------|
| sessions DDL + indexes | SI-020 | SI-020 + SI-090 fixture |
| scan_log DDL | SI-020 | SI-020 + SI-090 fixture |
| index_metadata DDL | SI-020 | SI-020 + SI-090 fixture |
| session_artifacts DDL + migration | SI-020 | SI-020 + SI-040 + SI-090 fixture |
| PRAGMA 配置 | SI-030 | SI-030 + SI-090 fixture |
| Schema version 策略 | SI-020 | SI-020 |
