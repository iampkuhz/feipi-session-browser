package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;

/**
 * StopCommand 契约测试。
 *
 * <p>验证 stop 子命令的 CLI 参数解析、PID 文件处理、进程终止和退出码行为。 使用 {@link ServerLifecycle} 在随机端口启动真实服务器， 然后验证 stop
 * 命令的完整流程。
 */
@DisplayName("StopCommand 契约测试")
class StopCommandTest {

  @TempDir Path tempDir;

  /** 运行 CLI 命令并捕获输出结果。 */
  private static CliExecution execute(String... args) {
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    ByteArrayOutputStream stderrBytes = new ByteArrayOutputStream();
    PrintStream origOut = System.out;
    PrintStream origErr = System.err;
    int exitCode;
    try {
      System.setOut(new PrintStream(stdoutBytes));
      System.setErr(new PrintStream(stderrBytes));
      exitCode = new CommandLine(new SessionBrowserCommand()).execute(args);
    } finally {
      System.setOut(origOut);
      System.setErr(origErr);
    }
    return new CliExecution(stdoutBytes.toString().trim(), stderrBytes.toString().trim(), exitCode);
  }

  /** 单次 CLI 执行的输出捕获结果。 */
  private record CliExecution(String stdout, String stderr, int exitCode) {}

  // ===== help 契约 =====

  @Nested
  @DisplayName("stop --help 输出契约")
  class StopHelpContract {

    @Test
    @DisplayName("stop --help 输出到 stdout，exit code = 0")
    void stopHelpShowsOptions() {
      CliExecution result = execute("stop", "--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("stop");
      assertThat(result.stdout()).contains("--port");
    }

    @Test
    @DisplayName("stop -h 输出到 stdout，exit code = 0")
    void stopShortHelp() {
      CliExecution result = execute("stop", "-h");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("stop");
    }
  }

  // ===== PID 文件缺失契约 =====

  @Nested
  @DisplayName("stop 无 PID 文件行为")
  class StopNoPidFileContract {

    @Test
    @DisplayName("无 PID 文件且端口无监听时，exit code = 0 并提示未运行")
    void noPidFileNoPortListening() {
      Path indexDir = tempDir.resolve("empty-index");

      CliExecution result =
          execute("stop", "--index-dir", indexDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stdout()).contains("未在运行");
    }

    @Test
    @DisplayName("无 PID 文件但端口有监听时，exit code = 1 并提示指定索引目录")
    void noPidFileButPortListening() throws Exception {
      // 启动一个真实服务器占用端口
      Path indexDir = tempDir.resolve("test-index");
      Files.createDirectories(indexDir);
      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int actualPort = lifecycle.start();

      try {
        // 用不同的 indexDir 运行 stop（不指向服务器的 indexDir）
        Path otherDir = tempDir.resolve("other-index");
        CliExecution result =
            execute(
                "stop",
                "--index-dir",
                otherDir.toAbsolutePath().toString(),
                "--port",
                "" + actualPort);

        assertThat(result.exitCode()).isEqualTo(1);
        assertThat(result.stderr()).contains("--index-dir");
      } finally {
        lifecycle.shutdown();
      }
    }
  }

  // ===== stale PID 契约 =====

  @Nested
  @DisplayName("stop stale PID 行为")
  class StopStalePidContract {

    @Test
    @DisplayName("PID 文件指向不存在的进程时，清理 PID 文件并 exit code = 0")
    void stalePidCleanedUp() throws Exception {
      Path indexDir = tempDir.resolve("stale-index");
      Files.createDirectories(indexDir);

      // 写入一个不存在的 PID（使用最大 PID 值，极不可能存在）
      PidFile.write(indexDir, Integer.MAX_VALUE, 0, "127.0.0.1");

      CliExecution result = execute("stop", "--index-dir", indexDir.toAbsolutePath().toString());

      assertThat(result.exitCode()).isZero();
      assertThat(result.stdout()).contains("stale PID");
      // PID 文件应被清理
      assertThat(PidFile.path(indexDir)).doesNotExist();
    }
  }

  // ===== 完整停止生命周期契约 =====

  @Nested
  @DisplayName("stop 完整停止生命周期")
  class StopLifecycleContract {

    @Test
    @DisplayName("serve 写入 PID 文件后 stop 可读取并清理（当前进程无法终止自身）")
    void serveWritePidThenStopTerminates() throws Exception {
      Path indexDir = tempDir.resolve("lifecycle-index");
      Files.createDirectories(indexDir);

      // 启动服务器
      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int actualPort = lifecycle.start();

      // 验证 PID 文件已写入
      assertThat(PidFile.path(indexDir)).exists();
      PidFile.Metadata meta = PidFile.read(indexDir);
      assertThat(meta).isNotNull();
      assertThat(meta.port()).isEqualTo(actualPort);
      assertThat(meta.host()).isEqualTo("127.0.0.1");
      assertThat(meta.pid()).isEqualTo(ProcessHandle.current().pid());

      // 直接调用 StopCommand 的 call() 方法执行 stop
      // 注意：stop 和 server 在同一 JVM，Java 禁止 destroy 当前进程
      // terminateProcess 会捕获 IllegalStateException 并返回，PID 文件仍被清理
      StopCommand stopCmd = new StopCommand();
      setField(stopCmd, "port", actualPort);
      setField(stopCmd, "indexDirOption", indexDir.toAbsolutePath().toString());
      setField(stopCmd, "force", false);
      int exitCode = stopCmd.call();

      assertThat(exitCode).isZero();

      // 验证 PID 文件已清理
      assertThat(PidFile.path(indexDir)).doesNotExist();

      // 清理：手动关闭服务器（因为 stop 无法终止当前 JVM）
      lifecycle.shutdown();
    }

    @Test
    @DisplayName("stop 幂等：重复 stop 不抛异常")
    void stopIsIdempotent() throws Exception {
      Path indexDir = tempDir.resolve("idempotent-index");
      Files.createDirectories(indexDir);

      // 写入一个不存在的 PID
      PidFile.write(indexDir, Integer.MAX_VALUE, 0, "127.0.0.1");

      // 第一次 stop：清理 stale PID
      StopCommand stopCmd1 = new StopCommand();
      setField(stopCmd1, "port", 0);
      setField(stopCmd1, "indexDirOption", indexDir.toAbsolutePath().toString());
      setField(stopCmd1, "force", false);
      int exitCode1 = stopCmd1.call();

      // 第二次 stop：PID 文件已不存在
      StopCommand stopCmd2 = new StopCommand();
      setField(stopCmd2, "port", 0);
      setField(stopCmd2, "indexDirOption", indexDir.toAbsolutePath().toString());
      setField(stopCmd2, "force", false);
      int exitCode2 = stopCmd2.call();

      assertThat(exitCode1).isZero();
      assertThat(exitCode2).isZero();
    }
  }

  // ===== health endpoint 验证契约 =====

  @Nested
  @DisplayName("health endpoint 验证")
  class HealthVerificationContract {

    @Test
    @DisplayName("checkHealthEndpoint 对运行中的服务器返回 true")
    void healthCheckOnRunningServer() throws Exception {
      Path indexDir = tempDir.resolve("health-index");
      Files.createDirectories(indexDir);

      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int actualPort = lifecycle.start();

      try {
        boolean result =
            StopCommand.checkHealthEndpoint("http://127.0.0.1:" + actualPort + "/healthz");
        assertThat(result).isTrue();
      } finally {
        lifecycle.shutdown();
      }
    }

    @Test
    @DisplayName("checkHealthEndpoint 对无效 URL 返回 false")
    void healthCheckOnInvalidUrl() {
      boolean result = StopCommand.checkHealthEndpoint("http://127.0.0.1:1/nonexistent");
      assertThat(result).isFalse();
    }

    @Test
    @DisplayName("isPortListening 对运行中的服务器返回 true")
    void portListeningOnRunningServer() throws Exception {
      Path indexDir = tempDir.resolve("port-index");
      Files.createDirectories(indexDir);

      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int actualPort = lifecycle.start();

      try {
        assertThat(StopCommand.isPortListening(actualPort)).isTrue();
      } finally {
        lifecycle.shutdown();
      }
    }

    @Test
    @DisplayName("isPortListening 对无效端口返回 false")
    void portListeningOnInvalidPort() {
      assertThat(StopCommand.isPortListening(0)).isFalse();
      assertThat(StopCommand.isPortListening(-1)).isFalse();
      assertThat(StopCommand.isPortListening(70000)).isFalse();
    }

    @Test
    @DisplayName("isPortListening 对未使用的端口返回 false")
    void portListeningOnUnusedPort() {
      // 端口 19999 极大概率未被使用
      assertThat(StopCommand.isPortListening(19999)).isFalse();
    }
  }

  // ===== 参数校验契约 =====

  @Nested
  @DisplayName("stop 参数校验")
  class StopParameterContract {

    @Test
    @DisplayName("无效端口号被 Picocli 拒绝")
    void invalidPortRejected() {
      CliExecution result = execute("stop", "--port", "abc");
      assertThat(result.exitCode()).isNotZero();
    }

    @Test
    @DisplayName("未知选项被拒绝")
    void unknownOptionRejected() {
      CliExecution result = execute("stop", "--unknown-flag");
      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }

  /** 通过反射设置 StopCommand 的私有字段（Picocli 在 CLI 外部使用时不会注入）。 */
  private static void setField(Object target, String fieldName, Object value) {
    try {
      var field = target.getClass().getDeclaredField(fieldName);
      field.setAccessible(true);
      field.set(target, value);
    } catch (Exception e) {
      throw new RuntimeException("设置字段失败: " + fieldName, e);
    }
  }
}
