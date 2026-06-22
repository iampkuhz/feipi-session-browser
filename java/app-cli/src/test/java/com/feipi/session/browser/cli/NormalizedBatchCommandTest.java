package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/**
 * {@link NormalizedBatchCommand} 单元测试。
 *
 * <p>验证隐藏命令的注册、空输入处理和命令配置。
 */
@DisplayName("NormalizedBatchCommand 测试")
class NormalizedBatchCommandTest {

  /**
   * 使用空 stdin 运行批量命令，并捕获 stdout 输出。
   *
   * @param args 命令行参数
   * @return stdout 输出内容
   */
  private static String runWithEmptyStdin(String... args) throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      // 设置空的 stdin
      System.setIn(new ByteArrayInputStream(new byte[0]));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute(args);

      assertThat(exitCode).isZero();
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
    return stdoutBytes.toString();
  }

  @Test
  @DisplayName("normalized-batch 存在于 subcommands 中")
  void commandRegistered() {
    CommandLine cmd = new CommandLine(new SessionBrowserCommand());
    assertThat(cmd.getSubcommands()).containsKey("normalized-batch");
  }

  @Test
  @DisplayName("normalized-batch 命令标记为隐藏")
  void commandIsHidden() {
    CommandLine cmd = new CommandLine(new SessionBrowserCommand());
    CommandLine subCmd = cmd.getSubcommands().get("normalized-batch");
    assertThat(subCmd.getCommandSpec().usageMessage().hidden()).isTrue();
  }

  @Test
  @DisplayName("空输入产生空输出")
  void emptyInputProducesEmptyOutput() throws Exception {
    String stdout = runWithEmptyStdin("normalized-batch", "--output-dir", "/tmp/batch-test-empty");
    assertThat(stdout).isEmpty();
  }

  @Test
  @DisplayName("未知 sourceId 输入产生错误输出")
  void unknownSourceIdProducesErrorOutput() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "{\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/nonexistent\"}\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-unknown");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).contains("error");
      assertThat(stdoutBytes.toString()).contains("Unknown source");
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }

  @Test
  @DisplayName("无效 JSON 输入产生错误输出")
  void invalidJsonProducesErrorOutput() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "not valid json\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-invalid");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).contains("error");
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }

  @Test
  @DisplayName("空行输入被跳过不产生输出")
  void emptyLinesAreSkipped() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "\n\n\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-emptylines");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).isEmpty();
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }
}
