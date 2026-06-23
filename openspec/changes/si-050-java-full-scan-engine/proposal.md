# SI-050: Java Full Scan Engine

## 动机

S3 stage 第五个任务。SI-040 已完成 artifact 到 index row 的映射。现在需要实现 Java 端的完整
full scan use case：session 发现、candidate 分类、artifact 生产和 index 写入。

## 范围

- 新增 `java/scan-engine` 模块
- `FullScanEngine` — 全量扫描 use case，协调发现、解析、归一化、制品写入和 index 写入
- `ScanConfig` — 扫描配置 record（源条目、artifact 输出目录、agent 过滤、并行度）
- `ScanSummary` — 扫描汇总 record（候选计数、per-source 分布、错误列表）
- `ScanIssue` — 扫描问题 record（会话键、源标识、阶段、消息）
- `ScanLogManager` — scan_log 表生命周期管理
- 复用现有组件：NormalizationEngine、NormalizedArtifactWriter、ArtifactRowMapper、WriteBatch
- 最小 CLI wiring：app-cli 添加 scan-engine 依赖
- 不修改 Python 代码或 web 模块

## 约束

- 不复制 parsing 逻辑，复用 source adapter SPI
- 每个 source family 有确定性排序（由 SourceAdapter.discover 保证）
- 单 SQLite writer，通过 WriteBatch 批量写入
- scan_log running/success/failure 事务语义
- 原始 source 文件只读
- 无 per-session JVM
- 大批量内存和 queue 有上限（WriteBatch 5000 条限制）
