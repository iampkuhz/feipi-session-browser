package com.feipi.session.browser.scan.engine;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 扫描阶段与候选进度日志；调用方须关闭实例，以等待单个 daemon 心跳线程退出。 */
public final class LoggingScanProgress implements ScanProgress, AutoCloseable {

  private static final Logger log = LoggerFactory.getLogger(LoggingScanProgress.class);
  static final long DEFAULT_HEARTBEAT_INTERVAL_MS = 30_000;

  private final long heartbeatIntervalMs;
  // 阶段、时间戳、日志和关闭状态由同一监视器保护，避免旧阶段日志越过结束/关闭边界。
  private Thread heartbeatThread;
  private Phase activePhase;
  private Phase sourcePhase;
  // 候选进度独立时间戳，仅由 onCandidateProcessed 和 onSourceStart 更新
  private long lastCandidateProgressNanos;
  // 心跳独立时间戳，仅由心跳线程更新
  private long lastHeartbeatLogNanos;
  private boolean closed;

  /**
   * 一致读取的扫描阶段快照。
   *
   * @param name 不含用户信息的阶段标识
   * @param startNanos 单调时钟起点
   */
  private record Phase(String name, long startNanos) {}

  /** 使用默认三十秒心跳间隔。 */
  public LoggingScanProgress() {
    this(DEFAULT_HEARTBEAT_INTERVAL_MS);
  }

  /** 供测试注入短间隔。 */
  LoggingScanProgress(long heartbeatIntervalMs) {
    if (heartbeatIntervalMs <= 0) {
      throw new IllegalArgumentException("heartbeatIntervalMs 须 > 0");
    }
    this.heartbeatIntervalMs = heartbeatIntervalMs;
  }

  @Override
  public synchronized void onPhaseStart(String phaseName) {
    if (closed) return;
    activePhase = new Phase(safePhase(phaseName), System.nanoTime());
    log.debug("扫描阶段开始: {}", activePhase.name());
    ensureHeartbeatRunning();
  }

  @Override
  public synchronized void onPhaseEnd(String phaseName, long durationMs) {
    if (closed || activePhase == null || !activePhase.name().equals(safePhase(phaseName))) return;
    log.debug("扫描阶段完成: {} ({}ms)", activePhase.name(), durationMs);
    activePhase = sourcePhase;
  }

  @Override
  public synchronized void onSourceStart(String sourceName, int candidateCount) {
    if (closed) return;
    lastCandidateProgressNanos = System.nanoTime();
    sourcePhase = new Phase("process:" + safeSource(sourceName), lastCandidateProgressNanos);
    activePhase = sourcePhase;
    log.debug("开始处理源: {} ({} 个候选)", safeSource(sourceName), candidateCount);
    ensureHeartbeatRunning();
  }

  @Override
  public synchronized void onCandidateProcessed(String sourceName, int processed, int total) {
    if (closed) return;
    long now = System.nanoTime();
    boolean isLast = processed == total;
    boolean timeElapsed = (now - lastCandidateProgressNanos) / 1_000_000 >= heartbeatIntervalMs;
    if (isLast || timeElapsed) {
      lastCandidateProgressNanos = now;
      log.debug("扫描进度: {}/{} ({})", processed, total, safeSource(sourceName));
    }
  }

  @Override
  public synchronized void onSourceEnd(String sourceName, int successCount) {
    if (closed) return;
    activePhase = null;
    sourcePhase = null;
    log.debug("源处理完成: {} (成功 {})", safeSource(sourceName), successCount);
  }

  /** 幂等关闭；返回前真实等待线程终止，即使调用线程已被取消/中断。 */
  @Override
  public void close() {
    Thread thread;
    synchronized (this) {
      closed = true;
      activePhase = null;
      sourcePhase = null;
      thread = heartbeatThread;
      if (thread != null) thread.interrupt();
    }
    if (thread == null || thread.equals(Thread.currentThread())) return;
    boolean interrupted = false;
    while (thread.isAlive()) {
      try {
        thread.join();
      } catch (InterruptedException e) {
        interrupted = true;
      }
    }
    if (interrupted) Thread.currentThread().interrupt();
  }

  /** 保留实际线程引用，不能以清空引用冒充线程结束。 */
  synchronized boolean isHeartbeatAlive() {
    return heartbeatThread != null && heartbeatThread.isAlive();
  }

  private void ensureHeartbeatRunning() {
    if (heartbeatThread != null) return;
    heartbeatThread = new Thread(this::heartbeatLoop, "scan-heartbeat");
    heartbeatThread.setDaemon(true);
    heartbeatThread.start();
  }

  private void heartbeatLoop() {
    try {
      while (!Thread.currentThread().isInterrupted()) {
        Thread.sleep(heartbeatIntervalMs);
        synchronized (this) {
          if (closed) return;
          long now = System.nanoTime();
          // 若候选进度刚记录过（同一窗口内），跳过心跳避免重复
          if ((now - lastCandidateProgressNanos) / 1_000_000 < heartbeatIntervalMs) {
            continue;
          }
          // 若心跳刚记录过，跳过避免频繁
          if ((now - lastHeartbeatLogNanos) / 1_000_000 < heartbeatIntervalMs) {
            continue;
          }
          if (activePhase != null) {
            lastHeartbeatLogNanos = now;
            long elapsedSeconds = (now - activePhase.startNanos()) / 1_000_000_000;
            log.debug("扫描阶段心跳: {} 已运行 {}s", activePhase.name(), elapsedSeconds);
          }
        }
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
    }
  }

  private static String safeSource(String name) {
    return name != null && name.matches("[a-z][a-z0-9_]{0,39}") ? name : "unknown";
  }

  private static String safePhase(String name) {
    if (name == null) return "unknown";
    return switch (name) {
      case "schema", "load_fingerprints", "clear_index", "flush", "flush_final" -> name;
      default ->
          name.startsWith("discover:")
              ? "discover:" + safeSource(name.substring("discover:".length()))
              : "unknown";
    };
  }
}
