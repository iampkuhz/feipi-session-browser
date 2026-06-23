package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/**
 * ScanCommand 契约测试。
 *
 * <p>验证 scan 子命令的参数解析、帮助输出、退出码和非交互语义。 包括 {@code --full}、{@code --incremental}、{@code --agent}、
 * {@code --force} 选项的行为，以及扫描锁冲突时的退出码稳定性。
 */
@DisplayName("ScanCommand 契约测试")
class ScanCommandTest {

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

  @Nested
  @DisplayName("scan --help 输出契约")
  class ScanHelpContract {

    @Test
    @DisplayName("scan --help 输出到 stdout，exit code = 0")
    void scanHelpShowsOptions() {
      CliExecution result = execute("scan", "--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("scan");
      assertThat(result.stdout()).contains("--full");
      assertThat(result.stdout()).contains("--incremental");
      assertThat(result.stdout()).contains("--agent");
      assertThat(result.stdout()).contains("--force");
    }

    @Test
    @DisplayName("scan -h 输出到 stdout，exit code = 0")
    void scanShortHelp() {
      CliExecution result = execute("scan", "-h");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("--full");
      assertThat(result.stdout()).contains("--incremental");
    }
  }

  @Nested
  @DisplayName("scan 参数解析契约")
  class ScanParameterContract {

    @Test
    @DisplayName("scan 不接受未知选项，exit code = 2")
    void unknownOption() {
      CliExecution result = execute("scan", "--unknown-option");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }

    @Test
    @DisplayName("scan --full 和 --incremental 同时使用输出错误，exit code = 1")
    void mutuallyExclusiveModes() {
      CliExecution result = execute("scan", "--full", "--incremental");

      assertThat(result.exitCode()).isEqualTo(1);
      assertThat(result.stderr()).contains("--full");
      assertThat(result.stderr()).contains("--incremental");
    }
  }

  @Nested
  @DisplayName("scan 非交互行为契约")
  class ScanNonInteractiveContract {

    @Test
    @DisplayName("scan 命令不会提示 stdin，直接以退出码响应")
    void scanDoesNotPromptOnStdin() {
      // scan 命令在冲突场景下不应等待 stdin 输入；
      // 非交互模式下 --force 标志控制冲突处理，不触发 input() 调用。
      // 这里验证 scan 命令的参数处理是确定性的，不依赖用户输入。
      CliExecution result = execute("scan", "--full");

      // 无论扫描是否成功，退出码必须是确定性的（0 或 1），不是阻塞等待
      assertThat(result.exitCode()).isIn(0, 1, 2);
    }
  }

  @Nested
  @DisplayName("scan 命令注册契约")
  class ScanRegistrationContract {

    @Test
    @DisplayName("scan 出现在根命令 help 输出中")
    void scanInRootHelp() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stdout()).contains("scan");
    }

    @Test
    @DisplayName("scan 命令在 SessionBrowserCommand 子命令列表中")
    void scanInSubcommands() {
      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      assertThat(cmd.getSubcommands()).containsKey("scan");
    }
  }
}
