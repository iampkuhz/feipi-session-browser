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
 * ServeCommand 契约测试。
 *
 * <p>验证 serve 子命令的 CLI 参数解析、帮助输出、启动/关闭生命周期和错误处理。 使用内存数据库和随机端口确保测试隔离。
 */
@DisplayName("ServeCommand 契约测试")
class ServeCommandTest {

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
  @DisplayName("serve --help 输出契约")
  class ServeHelpContract {

    @Test
    @DisplayName("serve --help 输出到 stdout，exit code = 0")
    void serveHelpShowsOptions() {
      CliExecution result = execute("serve", "--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("serve");
      assertThat(result.stdout()).contains("--host");
      assertThat(result.stdout()).contains("--port");
      assertThat(result.stdout()).contains("--allow-empty");
      assertThat(result.stdout()).contains("--no-scan");
    }

    @Test
    @DisplayName("serve -h 输出到 stdout，exit code = 0")
    void serveShortHelp() {
      CliExecution result = execute("serve", "-h");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("serve");
    }
  }

  // ===== 生命周期契约 =====

  @Nested
  @DisplayName("serve 启动/关闭生命周期")
  class ServeLifecycleContract {

    @Test
    @DisplayName("--no-scan --allow-empty 启动后优雅关闭")
    void serveStartAndShutdown() throws Exception {
      Path indexDir = tempDir.resolve("test-index");
      Files.createDirectories(indexDir);

      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());

      int actualPort = lifecycle.start();
      assertThat(actualPort).isGreaterThan(0);
      assertThat(lifecycle.isRunning()).isTrue();
      assertThat(lifecycle.actualPort()).isEqualTo(actualPort);

      // 验证 PID 文件已写入
      assertThat(PidFile.path(indexDir)).exists();
      PidFile.Metadata meta = PidFile.read(indexDir);
      assertThat(meta).isNotNull();
      assertThat(meta.pid()).isEqualTo(ProcessHandle.current().pid());
      assertThat(meta.port()).isEqualTo(actualPort);
      assertThat(meta.host()).isEqualTo("127.0.0.1");

      // 验证 health endpoint 可用
      verifyHealthEndpoint(actualPort);

      lifecycle.shutdown();
      assertThat(lifecycle.isRunning()).isFalse();

      // 验证 PID 文件已清理
      assertThat(PidFile.path(indexDir)).doesNotExist();
    }

    @Test
    @DisplayName("shutdown 幂等：重复调用不抛异常")
    void shutdownIsIdempotent() throws Exception {
      Path indexDir = tempDir.resolve("test-index");
      Files.createDirectories(indexDir);

      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());

      lifecycle.start();
      lifecycle.shutdown();
      lifecycle.shutdown(); // 重复调用
      assertThat(lifecycle.isRunning()).isFalse();
    }

    @Test
    @DisplayName("启动失败时无资源泄漏（端口冲突场景）")
    void startupFailureNoLeak() throws Exception {
      Path indexDir = tempDir.resolve("test-index");
      Files.createDirectories(indexDir);

      // 先启动一个 server
      ServerLifecycle first = new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int firstPort = first.start();
      assertThat(first.isRunning()).isTrue();

      // 尝试绑定同一端口
      ServerLifecycle second =
          new ServerLifecycle(indexDir, "127.0.0.1", firstPort, true, true, Set.of());
      try {
        second.start();
        // 如果没有抛异常（某些 OS 可能允许），跳过断言
      } catch (Exception e) {
        // 启动失败应清理资源
        assertThat(second.isRunning()).isFalse();
      } finally {
        second.shutdown();
        first.shutdown();
      }
    }
  }

  // ===== 参数校验契约 =====

  @Nested
  @DisplayName("serve 参数校验")
  class ServeParameterContract {

    @Test
    @DisplayName("无效端口号被 Picocli 拒绝")
    void invalidPortRejected() {
      // Picocli 无法将非数字字符串解析为 int
      CliExecution result = execute("serve", "--port", "abc");

      assertThat(result.exitCode()).isNotZero();
    }

    @Test
    @DisplayName("未知选项被拒绝")
    void unknownOptionRejected() {
      CliExecution result = execute("serve", "--unknown-flag");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }

  /** 验证 health endpoint 返回 200。 */
  private static void verifyHealthEndpoint(int port) {
    try {
      java.net.URI uri = java.net.URI.create("http://127.0.0.1:" + port + "/healthz");
      java.net.HttpURLConnection conn = (java.net.HttpURLConnection) uri.toURL().openConnection();
      conn.setConnectTimeout(3000);
      conn.setReadTimeout(3000);
      int responseCode = conn.getResponseCode();
      conn.disconnect();
      assertThat(responseCode).isEqualTo(200);
    } catch (Exception e) {
      throw new RuntimeException("health endpoint 验证失败", e);
    }
  }
}
