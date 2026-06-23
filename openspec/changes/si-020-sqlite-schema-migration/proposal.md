# SI-020 Proposal: SQLite Schema、版本与可回滚 Migration

## Summary

实现显式、幂等、可测试的 Java schema/migration 基础设施，保持当前 DB 可升级和回滚。使用 Xerial SQLite JDBC 和显式 SQL，不引入 ORM。

## Changes

- `java/index-sqlite/` -- 新模块：schema migration 管理
  - `SchemaVersion` -- schema 版本号 record，独立于 scan logic version
  - `Migration` -- 单条 migration 定义，SQL 从 classpath 资源加载
  - `MigrationRunner` -- 幂等 migration 执行器，原子事务
  - `IndexSchema` -- schema 入口，migration 注册和表结构验证
- `java/test-support/**/sqlite/` -- SQLite 测试辅助工具
- `java/contract-tests/**/schema/` -- schema 契约测试
- `sql/V001__initial_schema.sql` -- 初始 schema SQL 资源

## Scope

- 允许修改: java/index-sqlite/**, java/test-support/**/sqlite/**, java/contract-tests/**/schema/**, settings.gradle.kts, gradle/libs.versions.toml
- 禁止触碰: src/session_browser/**, java/web/**

## Risk

低风险。新模块无现有消费者；schema 与 Python 版完全对齐。
