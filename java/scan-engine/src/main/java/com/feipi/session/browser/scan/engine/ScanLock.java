package com.feipi.session.browser.scan.engine;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Objects;

/**
 * 跨进程扫描锁。
 *
 * <p>使用 OS 级文件锁协调同一机器上多个进程的扫描操作。 锁文件位于 {@code lockDir/scan.lock}，获取后写入持有者诊断信息（PID、owner 标签、启动时间），
 * 供被阻塞的进程读取诊断。
 *
 * <p>支持阻塞和非阻塞两种获取模式：
 *
 * <ul>
 *   <li>阻塞模式：等待直到获取成功或超时。
 *   <li>非阻塞模式：立即返回，获取失败时抛出 {@link ScanLockUnavailableException}。
 * </ul>
 *
 * <p>使用 try-with-resources 确保锁正确释放：
 *
 * <pre>{@code
 * try (ScanLock.ScanLockHandle handle = scanLock.acquire("foreground scan")) {
 *     // 扫描操作
 * }
 * }</pre>
 */
public final class ScanLock {

  private static final String LOCK_FILE_NAME = "scan.lock";
  private static final DateTimeFormatter LOCK_TIME_FORMAT =
      DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ").withZone(ZoneId.systemDefault());

  private final Path lockDir;

  /**
   * 创建扫描锁。
   *
   * @param lockDir 锁文件目录，不存在时自动创建
   */
  public ScanLock(Path lockDir) {
    this.lockDir = Objects.requireNonNull(lockDir, "lockDir 不得为 null");
  }

  /**
   * 获取锁文件路径。
   *
   * @return {@code lockDir/scan.lock}
   */
  public Path lockPath() {
    return lockDir.resolve(LOCK_FILE_NAME);
  }

  /**
   * 阻塞获取扫描锁。
   *
   * <p>等待直到获取成功或超过指定超时。获取成功后写入持有者诊断信息。
   *
   * @param owner 持有者标签，写入锁文件用于诊断
   * @param timeoutMs 最大等待时间（毫秒），0 表示不等待
   * @return 锁句柄，调用方负责关闭
   * @throws ScanLockUnavailableException 当超时后仍无法获取锁时
   * @throws IOException 当文件操作失败时
   */
  public ScanLockHandle acquire(String owner, long timeoutMs) throws IOException {
    Objects.requireNonNull(owner, "owner 不得为 null");
    Files.createDirectories(lockDir);

    Path path = lockPath();
    RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw");
    FileChannel channel = raf.getChannel();
    boolean acquired = false;
    long deadline = System.currentTimeMillis() + Math.max(0, timeoutMs);

    try {
      while (true) {
        FileLock lock = channel.tryLock();
        if (lock != null) {
          acquired = true;
          writeOwnerInfo(raf, owner);
          return new ScanLockHandle(raf, channel, lock);
        }

        if (System.currentTimeMillis() >= deadline) {
          String holder = readHolderInfo(path);
          throw new ScanLockUnavailableException(path, holder);
        }

        try {
          Thread.sleep(250);
        } catch (InterruptedException e) {
          Thread.currentThread().interrupt();
          throw new IOException("等待扫描锁被中断", e);
        }
      }
    } finally {
      if (!acquired) {
        closeQuietly(channel, raf);
      }
    }
  }

  /**
   * 非阻塞尝试获取扫描锁。
   *
   * <p>立即尝试获取，失败时返回 {@code null} 而不是抛异常。
   *
   * @param owner 持有者标签
   * @return 锁句柄，获取失败时返回 {@code null}
   * @throws IOException 当文件操作失败时
   */
  public ScanLockHandle tryLock(String owner) throws IOException {
    Objects.requireNonNull(owner, "owner 不得为 null");
    Files.createDirectories(lockDir);

    Path path = lockPath();
    RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw");
    FileChannel channel = raf.getChannel();
    FileLock lock = channel.tryLock();
    if (lock == null) {
      closeQuietly(channel, raf);
      return null;
    }

    writeOwnerInfo(raf, owner);
    return new ScanLockHandle(raf, channel, lock);
  }

  /**
   * 读取当前锁持有者信息。
   *
   * @return 持有者诊断字符串，无法读取时返回空串
   */
  public String readCurrentHolder() {
    return readHolderInfo(lockPath());
  }

  /** 写入持有者诊断信息到锁文件。 */
  private void writeOwnerInfo(RandomAccessFile raf, String owner) throws IOException {
    String timestamp = LOCK_TIME_FORMAT.format(Instant.now());
    String payload =
        "pid=" + ProcessHandle.current().pid() + " owner=" + owner + " started_at=" + timestamp;
    raf.seek(0);
    raf.setLength(0);
    raf.write(payload.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    raf.getChannel().force(true);
  }

  /** 从锁文件读取持有者信息。 */
  private static String readHolderInfo(Path path) {
    if (!Files.exists(path)) {
      return "";
    }
    try {
      byte[] bytes = Files.readAllBytes(path);
      return new String(bytes, java.nio.charset.StandardCharsets.UTF_8).trim();
    } catch (IOException e) {
      return "";
    }
  }

  /** 安静关闭 channel 和 file。 */
  private static void closeQuietly(FileChannel channel, RandomAccessFile raf) {
    try {
      channel.close();
    } catch (IOException ignored) {
    }
    try {
      raf.close();
    } catch (IOException ignored) {
    }
  }

  /**
   * 扫描锁句柄。
   *
   * <p>持有 OS 级文件锁。实现 {@link AutoCloseable}， 关闭时释放文件锁并关闭底层文件资源。
   */
  public static final class ScanLockHandle implements AutoCloseable {
    private final RandomAccessFile file;
    private final FileChannel channel;
    private final FileLock lock;

    ScanLockHandle(RandomAccessFile file, FileChannel channel, FileLock lock) {
      this.file = file;
      this.channel = channel;
      this.lock = lock;
    }

    @Override
    public void close() {
      try {
        lock.release();
      } catch (IOException ignored) {
      }
      try {
        channel.close();
      } catch (IOException ignored) {
      }
      try {
        file.close();
      } catch (IOException ignored) {
      }
    }
  }

  /**
   * 扫描锁不可用异常。
   *
   * <p>当无法在指定时间内获取扫描锁时抛出。 包含锁文件路径和当前持有者诊断信息。
   */
  public static final class ScanLockUnavailableException extends IOException {
    private static final long serialVersionUID = 1L;
    private final transient Path lockPath;
    private final String holder;

    ScanLockUnavailableException(Path lockPath, String holder) {
      super("扫描锁不可用: " + lockPath + (holder.isEmpty() ? "" : " (holder: " + holder + ")"));
      this.lockPath = lockPath;
      this.holder = holder;
    }

    /** 获取锁文件路径。 */
    public Path lockPath() {
      return lockPath;
    }

    /** 获取当前持有者诊断信息。 */
    public String holder() {
      return holder;
    }
  }
}
