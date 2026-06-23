package com.feipi.session.browser.scan.engine;

import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 扫描取消令牌。
 *
 * <p>提供线程安全的扫描取消信号。创建后传递给扫描引擎， 外部通过 {@link #cancel()} 发出取消请求，扫描引擎在循环中通过 {@link #isCancelled()}
 * 检查并提前终止。
 *
 * <p>一旦取消不可重置，保证单向语义。
 */
public final class ScanCancelToken {

  private final AtomicBoolean cancelled = new AtomicBoolean(false);

  /** 查询是否已取消。 */
  public boolean isCancelled() {
    return cancelled.get();
  }

  /** 发出取消信号。幂等操作。 */
  public void cancel() {
    cancelled.set(true);
  }

  /**
   * 如果已取消则抛出 {@link java.util.concurrent.CancellationException}。
   *
   * <p>扫描引擎在循环中调用此方法，检测到取消时立即终止处理。
   *
   * @throws java.util.concurrent.CancellationException 当已取消时
   */
  public void throwIfCancelled() {
    if (cancelled.get()) {
      throw new java.util.concurrent.CancellationException("扫描已取消");
    }
  }
}
