package com.feipi.session.browser.scan.engine;

import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
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
  // 锁定诊断内容以外的字节，避免 Windows 强制锁阻止读取；仍与旧版全文件锁重叠。
  // 文件锁允许超出 EOF，且不会扩展文件。
  private static final long LOCK_POSITION = Long.MAX_VALUE - 1;
  private static final DateTimeFormatter LOCK_TIME_FORMAT =
      DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssZ").withZone(ZoneId.systemDefault());

  // POSIX 上关闭同文件的其他 channel 可能释放本进程原生锁，因此只允许一个本地句柄。
  private static final Map<Path, ScanLockHandle> LOCAL_HANDLES = new HashMap<>();

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
    long deadline = System.currentTimeMillis() + Math.max(0, timeoutMs);
    while (true) {
      ScanLockHandle handle = tryLock(owner);
      if (handle != null) {
        return handle;
      }
      if (System.currentTimeMillis() >= deadline) {
        throw new ScanLockUnavailableException(lockPath(), readCurrentHolder());
      }
      try {
        Thread.sleep(250);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IOException("等待扫描锁被中断", e);
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

    Path path = lockDir.toRealPath().resolve(LOCK_FILE_NAME);
    synchronized (LOCAL_HANDLES) {
      if (findLocalHandle(path) != null) {
        return null;
      }
      ScanLockHandle handle = new ScanLockHandle(path);
      boolean acquired = false;
      try {
        if (!handle.acquire(owner)) {
          return null;
        }
        LOCAL_HANDLES.put(path, handle);
        acquired = true;
        return handle;
      } finally {
        if (!acquired) {
          handle.close();
        }
      }
    }
  }

  /** 调用方持有 LOCAL_HANDLES 监视器；仅查询文件身份，不打开额外的数据 channel。 */
  private static ScanLockHandle findLocalHandle(Path path) throws IOException {
    ScanLockHandle direct = LOCAL_HANDLES.get(path);
    if (direct != null || LOCAL_HANDLES.isEmpty() || Files.notExists(path)) {
      return direct;
    }
    for (ScanLockHandle handle : LOCAL_HANDLES.values()) {
      // 父目录 realpath 不足以识别最终文件的符号链接或硬链接别名。
      if (Files.isSameFile(path, handle.path)) {
        return handle;
      }
    }
    return null;
  }

  private static FileLock tryFileLock(FileChannel channel) throws IOException {
    try {
      return channel.tryLock(LOCK_POSITION, 1, false);
    } catch (OverlappingFileLockException e) {
      // 同 JVM 竞争与跨进程竞争遵循相同的非阻塞/超时语义。
      return null;
    }
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
  private static void writeOwnerInfo(RandomAccessFile raf, String owner) throws IOException {
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
    synchronized (LOCAL_HANDLES) {
      try {
        Path canonical = path.toAbsolutePath().getParent().toRealPath().resolve(LOCK_FILE_NAME);
        byte[] bytes = readOwnerBytes(findLocalHandle(canonical), canonical);
        return new String(bytes, java.nio.charset.StandardCharsets.UTF_8).trim();
      } catch (IOException e) {
        return "";
      }
    }
  }

  /** handle 为借用资源，由注册的 owner 关闭；这里只读取而不转移所有权。 */
  private static byte[] readOwnerBytes(ScanLockHandle handle, Path path) throws IOException {
    if (handle == null) {
      return Files.readAllBytes(path);
    }
    // 不额外打开/关闭 channel，以免释放同进程持有的 POSIX 锁。
    handle.file.seek(0);
    byte[] bytes = new byte[Math.toIntExact(handle.file.length())];
    handle.file.readFully(bytes);
    return bytes;
  }

  /**
   * 扫描锁句柄。
   *
   * <p>持有 OS 级文件锁。实现 {@link AutoCloseable}， 关闭时释放文件锁并关闭底层文件资源。
   */
  public static final class ScanLockHandle implements AutoCloseable {
    private final Path path;
    private final RandomAccessFile file;
    private FileLock lock;
    private boolean closed;

    ScanLockHandle(Path path) throws IOException {
      this.path = path;
      this.file = new RandomAccessFile(path.toFile(), "rw");
    }

    private boolean acquire(String owner) throws IOException {
      lock = tryFileLock(file.getChannel());
      if (lock == null) {
        return false;
      }
      writeOwnerInfo(file, owner);
      return true;
    }

    @Override
    public void close() {
      synchronized (LOCAL_HANDLES) {
        if (closed) {
          return;
        }
        closed = true;
        try {
          if (lock != null) {
            lock.release();
          }
        } catch (IOException ignored) {
        } finally {
          try {
            // RAF 拥有其 channel，关闭文件也关闭 channel 并释放剩余原生锁。
            file.close();
          } catch (IOException ignored) {
          } finally {
            // ScanLockHandle 保持 Object 的身份 equals，只移除当前句柄。
            LOCAL_HANDLES.remove(path, this);
          }
        }
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
