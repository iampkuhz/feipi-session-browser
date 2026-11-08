package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/**
 * CLI help/version 契约测试。
 *
 * <p>验证 no-arg、help、version、未知参数和多余参数的 stdout/stderr/exit code 行为矩阵。
 */
@DisplayName("CLI help/version 契约测试")
class CliContractTest {

  /**
   * 运行 CLI 命令并捕获输出结果。
   *
   * @param args 命令行参数
   * @return 包含 stdout、stderr 和退出码的结果记录
   */
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
  @DisplayName("--help / -h 输出契约")
  class HelpContract {

    @Test
    @DisplayName("--help 输出到 stdout，exit code = 0")
    void longHelpFlag() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
      assertThat(result.stdout()).contains("--help");
      assertThat(result.stdout()).contains("--version");
    }

    @Test
    @DisplayName("-h 输出到 stdout，exit code = 0")
    void shortHelpFlag() {
      CliExecution result = execute("-h");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
    }

    @Test
    @DisplayName("help 隐藏内部命令，且不展示无实现的桩命令")
    void helpShowsOnlyImplementedPublicCommands() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stdout()).doesNotContain("normalized-batch");
      assertThat(result.stdout())
          .contains("help")
          .contains("scan")
          .contains("serve")
          .contains("stop")
          .contains("status")
          .contains("doctor")
          .contains("deps")
          .contains("version")
          .contains("diagnose");
      assertThat(result.stdout())
          .doesNotContain("test")
          .doesNotContain("quality")
          .doesNotContain("release");
    }

    @Test
    @DisplayName("help 子命令输出公开 help，exit code = 0")
    void helpSubcommandShowsPublicHelp() {
      CliExecution result = execute("help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
      assertThat(result.stdout()).contains("--help");
      assertThat(result.stdout()).contains("--version");
      assertThat(result.stdout()).contains("scan").contains("serve").contains("stop");
      assertThat(result.stdout()).doesNotContain("normalized-batch");
    }
  }

  // ===== version 契约 =====

  @Nested
  @DisplayName("--version / -V 输出契约")
  class VersionContract {

    @Test
    @DisplayName("--version 输出到 stdout，exit code = 0")
    void longVersionFlag() {
      CliExecution result = execute("--version");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).matches("\\d+\\.\\d+(\\.\\d+)?(-[\\w.]+)?");
    }

    @Test
    @DisplayName("-V 输出到 stdout，exit code = 0")
    void shortVersionFlag() {
      CliExecution result = execute("-V");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).matches("\\d+\\.\\d+(\\.\\d+)?(-[\\w.]+)?");
    }

    @Test
    @DisplayName("BuildInfoVersionProvider 从 classpath 读取 app.version")
    void versionFromBuildInfo() throws Exception {
      String version = BuildInfoVersionProvider.readAppVersion();

      assertThat(version).isNotNull();
      assertThat(version).matches("\\d+\\.\\d+(\\.\\d+)?(-[\\w.]+)?");
    }

    @Test
    @DisplayName("--version 后跟多余参数输出错误到 stderr，exit code = 2")
    void versionFlagRejectsExtraArgs() {
      CliExecution result = execute("--version", "extra");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stdout()).isEmpty();
      assertThat(result.stderr()).contains("Unmatched argument");
      assertThat(result.stderr()).contains("extra");
    }
  }

  // ===== no-arg 契约 =====

  @Nested
  @DisplayName("无参数执行契约")
  class NoArgContract {

    @Test
    @DisplayName("无参数时输出提示信息到 stdout，exit code = 0")
    void noArgsShowsUsageHint() {
      CliExecution result = execute();

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("--help");
    }
  }

  // ===== 未知参数契约 =====

  @Nested
  @DisplayName("未知参数契约")
  class UnknownArgsContract {

    @Test
    @DisplayName("未知长选项输出错误到 stderr，exit code = 2")
    void unknownLongOption() {
      CliExecution result = execute("--unknown");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
      assertThat(result.stderr()).contains("--unknown");
    }

    @Test
    @DisplayName("未知短选项输出错误到 stderr，exit code = 2")
    void unknownShortOption() {
      CliExecution result = execute("-z");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }

  // ===== 多余参数契约 =====

  @Nested
  @DisplayName("多余参数契约")
  class ExtraArgsContract {

    @Test
    @DisplayName("多余位置参数输出错误到 stderr，exit code = 2")
    void extraPositionalArgs() {
      CliExecution result = execute("extra1", "extra2");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unmatched arguments");
    }

    @Test
    @DisplayName("合法选项后跟多余参数输出错误到 stderr，exit code = 2")
    void validOptionThenExtraArgs() {
      // 位置参数 "subcommand" 不被接受，Picocli 报参数不匹配错误
      CliExecution result = execute("subcommand");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unmatched argument");
    }
  }
}
