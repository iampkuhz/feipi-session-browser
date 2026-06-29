package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;

/**
 * DepsCommand 契约测试。
 *
 * <p>验证 Java deps 作为产品运行时 preflight 可独立执行，并给出 scan/serve 下一步语义。
 */
@DisplayName("DepsCommand 契约测试")
class DepsCommandTest {

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

  @Test
  @DisplayName("deps --help 输出 preflight 参数")
  void depsHelpShowsIndexDirOption() {
    CliExecution result = execute("deps", "--help");

    assertThat(result.exitCode()).isZero();
    assertThat(result.stderr()).isEmpty();
    assertThat(result.stdout()).contains("deps");
    assertThat(result.stdout()).contains("--index-dir");
  }

  @Test
  @DisplayName("deps 执行 Java/SQLite/运行时目录 preflight")
  void depsRunsRuntimePreflight() {
    Path dataDir = tempDir.resolve("runtime-index");

    CliExecution result = execute("deps", "--index-dir", dataDir.toAbsolutePath().toString());

    assertThat(result.exitCode()).isZero();
    assertThat(result.stderr()).isEmpty();
    assertThat(result.stdout()).contains("Java 运行时");
    assertThat(result.stdout()).contains("SQLite native library");
    assertThat(result.stdout()).contains("运行时目录");
    assertThat(result.stdout()).contains("scan 和 serve");
    assertThat(Files.isDirectory(dataDir)).isTrue();
  }
}
