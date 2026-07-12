package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/** diagnose 子命令 CLI 参数与退出码契约测试。 */
@DisplayName("diagnose 子命令契约测试")
class DiagnoseCommandContractTest {

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
    return new CliExecution(stdoutBytes.toString(), stderrBytes.toString(), exitCode);
  }

  private record CliExecution(String stdout, String stderr, int exitCode) {}

  @Test
  @DisplayName("diagnose --help 输出到 stdout，exit code = 0")
  void diagnoseHelp() {
    CliExecution result = execute("diagnose", "--help");
    assertThat(result.exitCode()).isEqualTo(0);
    assertThat(result.stdout()).contains("diagnose");
    assertThat(result.stdout()).contains("session");
  }

  @Test
  @DisplayName("diagnose session --help 显示参数说明，exit code = 0")
  void diagnoseSessionHelp() {
    CliExecution result = execute("diagnose", "session", "--help");
    assertThat(result.exitCode()).isEqualTo(0);
    assertThat(result.stdout()).contains("--agent");
    assertThat(result.stdout()).contains("--session-id");
    assertThat(result.stdout()).contains("--format");
  }

  @Test
  @DisplayName("diagnose session 缺少必填参数时 exit code = 2")
  void diagnoseSessionMissingArgs() {
    CliExecution result = execute("diagnose", "session");
    assertThat(result.exitCode()).isEqualTo(2);
  }

  @Test
  @DisplayName("diagnose session 不存在的 session 返回 exit code = 2")
  void diagnoseSessionNotFound() {
    CliExecution result =
        execute(
            "diagnose",
            "session",
            "--agent",
            "claude_code",
            "--session-id",
            "00000000-0000-0000-0000-000000000000",
            "--source-dir",
            "/nonexistent-dir-for-test");
    // source dir 不存在 → source ERROR → exit 2
    assertThat(result.exitCode()).isEqualTo(2);
  }

  @Test
  @DisplayName("diagnose session 支持 --format json")
  void diagnoseSessionJsonFormat() {
    CliExecution result =
        execute(
            "diagnose",
            "session",
            "--agent",
            "claude_code",
            "--session-id",
            "00000000-0000-0000-0000-000000000000",
            "--source-dir",
            "/nonexistent-dir-for-test",
            "--format",
            "json");
    // JSON 格式也应该正常输出（source ERROR 但 JSON 包含完整结构）
    assertThat(result.exitCode()).isEqualTo(2);
    assertThat(result.stdout()).contains("\"schemaVersion\"");
    assertThat(result.stdout()).contains("\"diagnose-session.v1\"");
  }
}
