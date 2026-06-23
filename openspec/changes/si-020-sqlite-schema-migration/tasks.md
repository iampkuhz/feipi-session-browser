# SI-020 Tasks

## SI-020 [IMPLEMENT] SQLite Schema、版本与可回滚 Migration

状态：完成

### 产物

- `java/index-sqlite/` 模块（SchemaVersion, Migration, MigrationRunner, IndexSchema）
- `java/index-sqlite/src/main/resources/sql/V001__initial_schema.sql`
- `java/test-support/**/sqlite/SqliteTestHelper.java`
- `java/contract-tests/**/schema/SchemaContractTest.java`
- OpenSpec change: `si-020-sqlite-schema-migration`
