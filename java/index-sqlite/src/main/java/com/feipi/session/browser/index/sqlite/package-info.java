/**
 * {@code index-sqlite} 模块：SQLite schema、连接运行时与 migration 管理。
 *
 * <p>本模块提供 SQLite index 的完整运行时基础设施：
 *
 * <h2>Schema 管理</h2>
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
 * <h2>连接运行时</h2>
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.index.sqlite.PragmaConfig} — PRAGMA
 *       配置：WAL、synchronous、busy_timeout、 foreign_keys。
 *   <li>{@link com.feipi.session.browser.index.sqlite.ConnectionFactory} — 连接工厂，创建并配置 JDBC 连接。
 *   <li>{@link com.feipi.session.browser.index.sqlite.WriteQueue} — 有界队列 + 单 writer 线程，保证写入串行化。
 *   <li>{@link com.feipi.session.browser.index.sqlite.WriteBatch} — 批量写入辅助，事务大小可配置。
 *   <li>{@link com.feipi.session.browser.index.sqlite.WriteTransaction} — 显式写事务，支持 commit/rollback。
 *   <li>{@link com.feipi.session.browser.index.sqlite.ReadTransaction} — 短生命周期只读事务，避免 WAL
 *       checkpoint starvation。
 *   <li>{@link com.feipi.session.browser.index.sqlite.IndexConnection} — 连接入口，组合 writer 连接和读连接工厂。
 * </ul>
 *
 * <h2>写入模型</h2>
 *
 * <p>所有写操作通过 {@link com.feipi.session.browser.index.sqlite.WriteQueue} 串行执行。 解析线程不得直接 commit，必须
 * submit 到 writer 队列。 批量事务大小由 {@link com.feipi.session.browser.index.sqlite.WriteBatch}
 * 控制，防止单次事务过大。
 *
 * <h2>校验放置</h2>
 *
 * <p>schema version 和 PRAGMA 配置校验位于连接层边界。 下游 repository/query 使用已验证的连接和 schema，不重复检查。
 */
package com.feipi.session.browser.index.sqlite;
