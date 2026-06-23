package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.SQLException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * SQLite index 连接入口。
 *
 * <p>管理 writer 连接、{@link WriteQueue} 和 read-only 连接工厂。 写入通过 {@link #writeQueue} 串行执行，读取通过 {@link
 * #readTransaction} 并行执行。
 *
 * <p>writer 连接独占于 {@link WriteQueue} 的 writer 线程，其他线程不得直接使用。 read 连接由 {@link ConnectionFactory}
 * 按需创建，每个 {@link ReadTransaction} 持有独立连接。
 *
 * <p>关闭语义：{@link #close} 先关闭 {@link WriteQueue}（等待排队的写操作完成），再关闭 writer 连接。
 */
public final class IndexConnection implements AutoCloseable {

  private static final Logger log = LoggerFactory.getLogger(IndexConnection.class);

  private final Connection writerConnection;
  private final ConnectionFactory readFactory;
  private final PragmaConfig pragmaConfig;
  private final WriteQueue writeQueue;
  private volatile boolean closed;

  /**
   * 使用已有连接和读连接工厂创建。
   *
   * @param writerConnection writer 连接，由 WriteQueue 独占
   * @param readFactory 读连接工厂
   * @param pragmaConfig PRAGMA 配置
   */
  public IndexConnection(
      Connection writerConnection, ConnectionFactory readFactory, PragmaConfig pragmaConfig) {
    if (writerConnection == null) {
      throw new IllegalArgumentException("writerConnection 不能为 null");
    }
    if (readFactory == null) {
      throw new IllegalArgumentException("readFactory 不能为 null");
    }
    if (pragmaConfig == null) {
      throw new IllegalArgumentException("pragmaConfig 不能为 null");
    }
    this.writerConnection = writerConnection;
    this.readFactory = readFactory;
    this.pragmaConfig = pragmaConfig;
    this.writeQueue = new WriteQueue(writerConnection);
  }

  /**
   * 使用已有连接创建，读连接工厂复用相同 JDBC URL 和 PRAGMA。
   *
   * @param writerConnection writer 连接
   * @param pragmaConfig PRAGMA 配置
   * @param jdbcUrl 读连接 JDBC URL
   * @return 新 IndexConnection
   */
  public static IndexConnection create(
      Connection writerConnection, PragmaConfig pragmaConfig, String jdbcUrl) {
    ConnectionFactory readFactory = new ConnectionFactory(jdbcUrl, pragmaConfig);
    return new IndexConnection(writerConnection, readFactory, pragmaConfig);
  }

  /**
   * 使用已有连接和默认 PRAGMA 创建。
   *
   * @param writerConnection writer 连接
   * @param jdbcUrl 读连接 JDBC URL
   * @return 新 IndexConnection
   */
  public static IndexConnection withDefaults(Connection writerConnection, String jdbcUrl) {
    return create(writerConnection, PragmaConfig.DEFAULTS, jdbcUrl);
  }

  /**
   * 开启短生命周期只读事务。
   *
   * <p>创建独立读连接，在 REPEATABLE READ 隔离级别执行。 返回的 {@link ReadTransaction} 必须在使用后关闭。
   *
   * @return 只读事务
   * @throws SQLException 连接创建或 PRAGMA 配置失败
   */
  public ReadTransaction readTransaction() throws SQLException {
    ensureOpen();
    Connection readConn = readFactory.create();
    return new ReadTransaction(readConn);
  }

  /**
   * 获取 writer 队列。
   *
   * <p>所有写操作通过此队列串行执行。
   *
   * @return writer 队列
   */
  public WriteQueue writeQueue() {
    ensureOpen();
    return writeQueue;
  }

  /**
   * 获取 writer 连接。
   *
   * <p>仅供 {@link WriteQueue} 和内部使用。外部代码不得直接操作此连接。
   *
   * @return writer 连接
   */
  public Connection writerConnection() {
    return writerConnection;
  }

  /** 获取 PRAGMA 配置。 */
  public PragmaConfig pragmaConfig() {
    return pragmaConfig;
  }

  /**
   * 关闭连接。
   *
   * <p>先关闭 {@link WriteQueue}（等待排队的写操作完成）， 再关闭 writer 连接。关闭幂等，多次调用安全。
   */
  @Override
  public void close() {
    if (closed) {
      return;
    }
    closed = true;
    try {
      writeQueue.shutdown();
    } catch (Exception e) {
      log.warn("关闭 WriteQueue 失败", e);
    }
    try {
      writerConnection.close();
    } catch (SQLException e) {
      log.warn("关闭 writer 连接失败", e);
    }
  }

  /** 检查连接是否已关闭。 */
  private void ensureOpen() {
    if (closed) {
      throw new IllegalStateException("IndexConnection 已关闭");
    }
  }
}
