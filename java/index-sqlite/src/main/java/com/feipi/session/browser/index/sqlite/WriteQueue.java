package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 有界队列与单 writer 执行器。
 *
 * <p>所有写入操作通过本类串行执行，保证同一时刻只有一个 writer 线程访问数据库。 解析线程不得直接 commit，必须通过 {@link #submit} 将写操作排入队列。
 *
 * <p>队列有界（{@link #DEFAULT_QUEUE_CAPACITY} = 64），满时 {@link #submit} 阻塞等待空间。 批量事务大小由 {@link
 * WriteBatch} 控制。
 *
 * <p>关闭语义：调用 {@link #shutdown} 后不再接受新任务，等待已排队任务完成后关闭 writer 连接。 {@link #cancelPending} 立即拒绝
 * 所有待处理任务。
 */
public final class WriteQueue {

  private static final Logger log = LoggerFactory.getLogger(WriteQueue.class);

  /** 默认队列容量。 */
  public static final int DEFAULT_QUEUE_CAPACITY = 64;

  /** 默认批量上限。 */
  public static final int DEFAULT_BATCH_LIMIT = WriteBatch.DEFAULT_MAX_ENTRIES;

  private final ArrayBlockingQueue<Runnable> queue;
  private final Connection writerConnection;
  private final Thread writerThread;
  private final AtomicBoolean running = new AtomicBoolean(true);
  private final int batchLimit;
  private volatile Throwable writerError;
  private final CountDownLatch writerStopped = new CountDownLatch(1);

  /**
   * 创建 writer 队列。
   *
   * <p>启动后台 writer 线程，从队列中逐个取任务执行。 writer 线程独占 {@code writerConnection}，其他线程不得直接使用该连接。
   *
   * @param writerConnection 写连接，由 writer 线程独占
   * @param queueCapacity 队列容量
   * @param batchLimit 单批次最大语句数
   */
  public WriteQueue(Connection writerConnection, int queueCapacity, int batchLimit) {
    if (writerConnection == null) {
      throw new IllegalArgumentException("writerConnection 不能为 null");
    }
    if (queueCapacity <= 0) {
      throw new IllegalArgumentException("queueCapacity 必须 > 0");
    }
    if (batchLimit <= 0) {
      throw new IllegalArgumentException("batchLimit 必须 > 0");
    }
    this.writerConnection = writerConnection;
    this.batchLimit = batchLimit;
    this.queue = new ArrayBlockingQueue<>(queueCapacity);
    this.writerThread = new Thread(this::writerLoop, "sqlite-writer");
    this.writerThread.setDaemon(true);
    this.writerThread.start();
  }

  /** 使用默认容量创建 writer 队列。 */
  public WriteQueue(Connection writerConnection) {
    this(writerConnection, DEFAULT_QUEUE_CAPACITY, DEFAULT_BATCH_LIMIT);
  }

  /**
   * 提交写操作到队列。
   *
   * <p>队列满时阻塞等待空间。返回的 future 在 writer 线程完成操作后 resolve。 操作失败时 future 以 {@link SQLException} 异常完成。
   *
   * @param op 写操作
   * @return 操作完成 future
   */
  public CompletableFuture<Void> submit(WriteBatch.WriteOperation op) {
    CompletableFuture<Void> future = new CompletableFuture<>();
    Runnable task =
        () -> {
          try {
            op.execute(writerConnection);
            future.complete(null);
          } catch (SQLException e) {
            future.completeExceptionally(e);
          }
        };
    try {
      while (running.get()) {
        if (queue.offer(task, 100, TimeUnit.MILLISECONDS)) {
          return future;
        }
      }
      future.completeExceptionally(new IllegalStateException("writer queue 已关闭"));
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      future.completeExceptionally(e);
    }
    return future;
  }

  /**
   * 创建批量写入器。
   *
   * <p>返回的 WriteBatch 必须在 {@link WriteBatch.WriteOperation} 中使用， 由 writer 线程执行。
   *
   * @return 新的批量写入器
   */
  public WriteBatch newBatch() {
    return new WriteBatch(writerConnection, batchLimit);
  }

  /**
   * 优雅关闭。
   *
   * <p>不再接受新任务，等待已排队任务完成后退出 writer 线程。 如果 writer 线程已因异常退出，抛出该异常。
   *
   * @throws SQLException writer 线程因 SQL 错误退出
   * @throws InterruptedException 等待中断
   */
  public void shutdown() throws SQLException, InterruptedException {
    running.set(false);
    writerStopped.await(30, TimeUnit.SECONDS);
    if (writerError != null) {
      throw new SQLException("writer 线程异常退出", writerError);
    }
  }

  /**
   * 立即取消所有待处理任务。
   *
   * <p>中断 writer 线程，拒绝队列中所有未执行任务。 正在执行的任务可能被中断。
   */
  public void cancelPending() {
    running.set(false);
    List<Runnable> remaining = new ArrayList<>();
    queue.drainTo(remaining);
    for (Runnable task : remaining) {
      task.run();
    }
    writerThread.interrupt();
  }

  /** 获取队列中待处理任务数。 */
  public int pendingCount() {
    return queue.size();
  }

  /** 获取批量上限。 */
  public int batchLimit() {
    return batchLimit;
  }

  /**
   * 获取 writer 连接。
   *
   * <p>仅供 WriteQueue 内部和 WriteBatch 使用。 外部代码不得直接操作此连接。
   */
  Connection writerConnection() {
    return writerConnection;
  }

  /** writer 线程主循环。 */
  private void writerLoop() {
    try {
      while (running.get() || !queue.isEmpty()) {
        Runnable task;
        try {
          task = queue.poll(100, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          break;
        }
        if (task != null) {
          task.run();
        }
      }
    } catch (RuntimeException e) {
      writerError = e;
      log.error("writer 线程异常退出", e);
    } finally {
      writerStopped.countDown();
    }
  }
}
