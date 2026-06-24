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
 * StatusCommand 契约测试。
 *
 * <p>验证 status 子命令的行为：help 输出、PID 文件存在/缺失、stale PID 和端口探测。
 */
@DisplayName("StatusCommand 契约测试")
class StatusCommandTest {

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
  @DisplayName("status --help 输出契约")
  class StatusHelpContract {

    @Test
    @DisplayName("status --help 输出到 stdout，exit code = 0")
    void statusHelpShowsOptions() {
      CliExecution result = execute("status", "--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("status");
      assertThat(result.stdout()).contains("--port");
      assertThat(result.stdout()).contains("--index-dir");
    }
  }

  // ===== 未运行状态契约 =====

  @Nested
  @DisplayName("status 服务未运行行为")
  class StatusNotRunningContract {

    @Test
    @DisplayName("无 PID 文件且端口无监听时，exit code = 1 并提示未运行")
    void noPidFileNoPort() {
      Path indexDir = tempDir.resolve("empty-index");

      CliExecution result =
          execute("status", "--index-dir", indexDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.exitCode()).isEqualTo(1);
      assertThat(result.stdout()).contains("未运行");
    }

    @Test
    @DisplayName("stale PID 文件时，exit code = 1 并提示 stale")
    void stalePidFile() throws Exception {
      Path indexDir = tempDir.resolve("stale-index");
      Files.createDirectories(indexDir);

      // 写入一个不存在的 PID
      PidFile.write(indexDir, Integer.MAX_VALUE, 0, "127.0.0.1");

      CliExecution result = execute("status", "--index-dir", indexDir.toAbsolutePath().toString());

      assertThat(result.exitCode()).isEqualTo(1);
      assertThat(result.stdout()).contains("stale");
    }
  }

  // ===== 运行中状态契约 =====

  @Nested
  @DisplayName("status 服务运行中行为")
  class StatusRunningContract {

    @Test
    @DisplayName("serve 启动后 status 显示运行中并输出 PID 和端口")
    void statusShowsRunning() throws Exception {
      Path indexDir = tempDir.resolve("running-index");
      Files.createDirectories(indexDir);

      ServerLifecycle lifecycle =
          new ServerLifecycle(indexDir, "127.0.0.1", 0, true, true, Set.of());
      int actualPort = lifecycle.start();

      try {
        CliExecution result =
            execute(
                "status",
                "--index-dir",
                indexDir.toAbsolutePath().toString(),
                "--port",
                "" + actualPort);

        assertThat(result.exitCode()).isZero();
        assertThat(result.stdout()).contains("运行中");
        assertThat(result.stdout()).contains("PID");
        assertThat(result.stdout()).contains("" + actualPort);
      } finally {
        lifecycle.shutdown();
      }
    }
  }

  // ===== 参数校验契约 =====

  @Nested
  @DisplayName("status 参数校验")
  class StatusParameterContract {

    @Test
    @DisplayName("无效端口号被 Picocli 拒绝")
    void invalidPortRejected() {
      CliExecution result = execute("status", "--port", "abc");
      assertThat(result.exitCode()).isNotZero();
    }

    @Test
    @DisplayName("未知选项被拒绝")
    void unknownOptionRejected() {
      CliExecution result = execute("status", "--unknown-flag");
      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }

  // ===== help 中 status 出现契约 =====

  @Nested
  @DisplayName("status 在主 help 中可见")
  class StatusInMainHelp {

    @Test
    @DisplayName("根 --help 输出包含 status 命令")
    void mainHelpContainsStatus() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stdout()).contains("status");
    }
  }
}
