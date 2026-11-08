package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link ScanLock} 单元测试。
 *
 * <p>覆盖锁获取/释放、非阻塞 tryLock、锁文件诊断信息、锁不可用异常。 使用真实文件系统测试跨进程锁语义（同一 JVM 内通过 FileLock 互斥）。
 */
class ScanLockTest {

  @TempDir Path tempDir;

  @Test
  void acquireAndRelease() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    assertThat(lock.lockPath()).isEqualTo(tempDir.resolve("scan.lock"));

    try (ScanLock.ScanLockHandle handle = lock.acquire("test-owner", 1000)) {
      assertThat(handle).isNotNull();
      assertThat(Files.exists(lock.lockPath())).isTrue();
      // 锁文件应包含 owner 信息
      String content = Files.readString(lock.lockPath());
      assertThat(content).contains("owner=test-owner");
      assertThat(content).contains("pid=");
      assertThat(content).contains("started_at=");
    }
  }

  @Test
  void tryLockSucceedsWhenNoContention() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    try (ScanLock.ScanLockHandle handle = lock.tryLock("try-owner")) {
      assertThat(handle).isNotNull();
      String content = Files.readString(lock.lockPath());
      assertThat(content).contains("owner=try-owner");
    }
  }

  @Test
  void tryLockReturnsNullUnderContention() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    try (ScanLock.ScanLockHandle outer = lock.acquire("holder", 1000)) {
      assertThat(outer).isNotNull();
      for (int i = 0; i < 20; i++) {
        assertThat(new ScanLock(tempDir).tryLock("contender")).isNull();
        assertThatThrownBy(() -> lock.acquire("contender", 0))
            .isInstanceOf(ScanLock.ScanLockUnavailableException.class);
      }
      assertThat(lock.readCurrentHolder()).contains("owner=holder");
    }
    Files.delete(lock.lockPath());
    assertThat(lock.lockPath()).doesNotExist();
  }

  @Test
  void localContentionAndDiagnosticsDoNotReleaseCrossProcessLock() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    Path probe = tempDir.resolve("ScanLockProbe.java");
    Files.writeString(
        probe,
        """
        import java.nio.channels.FileChannel;
        import java.nio.channels.FileLock;
        import java.nio.file.Path;
        import java.nio.file.StandardOpenOption;

        class ScanLockProbe {
          public static void main(String[] args) throws Exception {
            try (FileChannel channel = FileChannel.open(Path.of(args[0]), StandardOpenOption.WRITE);
                FileLock lock = channel.tryLock()) {
              System.out.println(lock == null ? "BLOCKED" : "ACQUIRED");
            }
          }
        }
        """);
    Path aliasDir = Files.createDirectory(tempDir.resolve("alias"));
    ScanLock alias = new ScanLock(aliasDir);
    Files.createFile(lock.lockPath());
    Files.createLink(alias.lockPath(), lock.lockPath());
    try (ScanLock.ScanLockHandle holder = lock.acquire("native-owner", 1000)) {
      assertThat(holder).isNotNull();
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThat(new ScanLock(tempDir).tryLock("local-loser")).isNull();
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThatThrownBy(() -> new ScanLock(tempDir).acquire("local-timeout", 250))
          .isInstanceOf(ScanLock.ScanLockUnavailableException.class);
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThat(new ScanLock(tempDir).readCurrentHolder()).contains("owner=native-owner");
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThat(alias.tryLock("alias-loser")).isNull();
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThatThrownBy(() -> alias.acquire("alias-timeout", 250))
          .isInstanceOf(ScanLock.ScanLockUnavailableException.class)
          .hasMessageContaining("owner=native-owner");
      assertProbeResult(probe, lock.lockPath(), "BLOCKED");
      assertThat(alias.readCurrentHolder()).contains("owner=native-owner");
      assertProbeResult(probe, alias.lockPath(), "BLOCKED");
    }
    assertProbeResult(probe, lock.lockPath(), "ACQUIRED");
    assertProbeResult(probe, alias.lockPath(), "ACQUIRED");
    Files.delete(alias.lockPath());
    Files.delete(lock.lockPath());
  }

  private static void assertProbeResult(Path probe, Path lockPath, String expected)
      throws Exception {
    Path java = Path.of(System.getProperty("java.home"), "bin", "java");
    if (!Files.exists(java)) {
      java = java.resolveSibling("java.exe");
    }
    Process process =
        new ProcessBuilder(java.toString(), probe.toString(), lockPath.toString())
            .redirectErrorStream(true)
            .start();
    try {
      assertThat(process.waitFor(30, TimeUnit.SECONDS)).isTrue();
      String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
      assertThat(process.exitValue()).as(output).isZero();
      assertThat(output.lines().toList()).contains(expected);
    } finally {
      if (process.isAlive()) {
        process.destroyForcibly();
        assertThat(process.waitFor(10, TimeUnit.SECONDS)).isTrue();
      }
    }
  }

  @Test
  void acquireCreatesLockDirectory() throws Exception {
    Path subDir = tempDir.resolve("sub/lock/dir");
    ScanLock lock = new ScanLock(subDir);
    try (ScanLock.ScanLockHandle handle = lock.acquire("dir-test", 1000)) {
      assertThat(handle).isNotNull();
      assertThat(Files.isDirectory(subDir)).isTrue();
      assertThat(Files.exists(subDir.resolve("scan.lock"))).isTrue();
    }
  }

  @Test
  void releaseAllowsReacquire() throws Exception {
    ScanLock lock = new ScanLock(tempDir);

    try (ScanLock.ScanLockHandle handle = lock.acquire("first", 1000)) {
      assertThat(handle).isNotNull();
    }

    // 释放后应能再次获取
    try (ScanLock.ScanLockHandle handle = lock.acquire("second", 1000)) {
      assertThat(handle).isNotNull();
      String content = Files.readString(lock.lockPath());
      assertThat(content).contains("owner=second");
    }
  }

  @Test
  void readCurrentHolderReturnsWrittenInfo() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    ScanLock.ScanLockHandle handle = lock.acquire("reader-test", 1000);
    try {
      String holder = lock.readCurrentHolder();
      assertThat(holder).contains("owner=reader-test");
      assertThat(holder).contains("pid=");
    } finally {
      handle.close();
    }
  }

  @Test
  void readCurrentHolderReturnsEmptyForMissingFile() {
    Path emptyDir = tempDir.resolve("nonexistent");
    ScanLock lock = new ScanLock(emptyDir);
    assertThat(lock.readCurrentHolder()).isEmpty();
  }

  @Test
  void nullOwnerThrows() {
    ScanLock lock = new ScanLock(tempDir);
    assertThatThrownBy(() -> lock.acquire(null, 1000)).isInstanceOf(NullPointerException.class);
  }

  @Test
  void nullLockDirThrows() {
    assertThatThrownBy(() -> new ScanLock(null)).isInstanceOf(NullPointerException.class);
  }
}
