/**
 * {@code index-sqlite} 模块：SQLite schema 管理与可回滚 migration。
 *
 * <p>本模块提供显式、幂等、可测试的 schema migration 基础设施：
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.index.sqlite.SchemaVersion} — schema 版本号，独立于 scan logic
 *       version。
 *   <li>{@link com.feipi.session.browser.index.sqlite.Migration} — 单条 migration 定义，SQL 从 classpath
 *       资源加载。
 *   <li>{@link com.feipi.session.browser.index.sqlite.MigrationRunner} — 幂等 migration 执行器，原子事务。
 *   <li>{@link com.feipi.session.browser.index.sqlite.IndexSchema} — schema 入口，注册 migration 并验证表结构。
 * </ul>
 *
 * <h2>校验放置</h2>
 *
 * <p>schema version 和表结构完整性校验位于 migration manager 边界（本模块）。 下游 repository/query 使用已验证
 * schema，不重复检查列是否存在。
 *
 * <h2>S3 契约</h2>
 *
 * <p>schema version 与 scan logic version 独立演进。 schema migration 原子事务；失败回滚，不留下半升级。
 */
package com.feipi.session.browser.index.sqlite;
