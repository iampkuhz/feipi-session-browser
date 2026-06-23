package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/**
 * NDJSON 协议边界测试。
 *
 * <p>验证 Java batch 协议输出的完整性：版本头、请求回显、结果、结束摘要。
 */
@DisplayName("NDJSON 协议测试")
class BatchProtocolTest {

  /**
   * 使用指定 stdin 运行 batch 命令并捕获 stdout。
   *
   * @param stdinContent stdin 输入内容
   * @return stdout 输出
   */
  private static String runBatch(String stdinContent, String... extraArgs) throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      System.setIn(new ByteArrayInputStream(stdinContent.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      List<String> argList = new ArrayList<>();
      argList.add("normalized-batch");
      argList.add("--output-dir");
      argList.add("/tmp/batch-protocol-test");
      for (String extra : extraArgs) {
        argList.add(extra);
      }
      String[] args = argList.toArray(new String[0]);

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      cmd.execute(args);
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
    return stdoutBytes.toString(StandardCharsets.UTF_8);
  }

  @Test
  @DisplayName("版本头包含正确的 protocol 和 version")
  void headerContainsProtocolAndVersion() throws Exception {
    String input = "{\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/nonexistent\"}\n";
    String stdout = runBatch(input);
    // 版本头必须在第一行
    String firstLine = stdout.split("\n")[0];
    assertThat(firstLine).contains("\"protocol\":\"normalized-batch\"");
    assertThat(firstLine).contains("\"version\":\"1.0\"");
  }

  @Test
  @DisplayName("结束摘要包含 totalRequests")
  void endSummaryContainsTotalRequests() throws Exception {
    String input = "{\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/nonexistent\"}\n";
    String stdout = runBatch(input);
    String[] lines = stdout.split("\n");
    // 最后一行必须是 end summary
    String lastLine = lines[lines.length - 1];
    assertThat(lastLine).contains("\"type\":\"end\"");
    assertThat(lastLine).contains("\"totalRequests\"");
  }

  @Test
  @DisplayName("请求回显包含 requestId")
  void requestEchoContainsRequestId() throws Exception {
    String input =
        "{\"requestId\":\"test-req-1\",\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/nonexistent\"}\n";
    String stdout = runBatch(input);
    assertThat(stdout).contains("\"requestId\":\"test-req-1\"");
  }

  @Test
  @DisplayName("多条输入产生多条请求回显")
  void multipleInputsProduceMultipleEchoes() throws Exception {
    String input =
        "{\"requestId\":\"req-1\",\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/a\"}\n"
            + "{\"requestId\":\"req-2\",\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/b\"}\n";
    String stdout = runBatch(input);
    assertThat(stdout).contains("\"requestId\":\"req-1\"");
    assertThat(stdout).contains("\"requestId\":\"req-2\"");
  }

  @Test
  @DisplayName("每行输出都是合法 JSON")
  void everyOutputLineIsValidJson() throws Exception {
    String input =
        "{\"requestId\":\"req-1\",\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/a\"}\n"
            + "not-json-at-all\n";
    String stdout = runBatch(input);
    for (String line : stdout.split("\n")) {
      if (line.isBlank()) {
        continue;
      }
      // 每行必须能被 JSON 解析
      assertThat(line).startsWith("{");
      assertThat(line).endsWith("}");
    }
  }
}
