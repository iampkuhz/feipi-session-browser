package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 实际内嵌 JRE 的正常 serve 启动回归，不替代真实来源统计验收。 */
class RuntimeServeSmokeTest {
  @TempDir Path temporary;

  @Test
  void embeddedRuntimeInitializesWebWithAutomaticScanning() throws Exception {
    String distribution = System.getProperty("cli.runtime.dir");
    assertThat(distribution).as("Gradle 必须提供本轮 runtime distribution").isNotBlank();
    boolean windows = System.getProperty("os.name").startsWith("Windows");
    Path root = Path.of(distribution).toAbsolutePath();
    Path launcher = root.resolve(windows ? "bin/run.bat" : "bin/run");
    assertThat(launcher).isRegularFile();
    assertThat(root.resolve(windows ? "runtime/bin/java.exe" : "runtime/bin/java")).isRegularFile();
    Path home = Files.createDirectory(temporary.resolve("home"));
    Path sessions = Files.createDirectories(home.resolve(".codex/sessions/2026/11/06"));
    Files.writeString(
        sessions.resolve("rollout-2026-11-06T00-00-00-11111111-2222-4333-8444-555555555555.jsonl"),
        """
        {"timestamp":"2026-11-06T00:00:00Z","type":"session_meta","payload":{"id":"11111111-2222-4333-8444-555555555555","cwd":"/synthetic/runtime-smoke","cli_version":"0.0.0","source":"cli"}}
        {"timestamp":"2026-11-06T00:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Synthetic runtime bootstrap question"}]}}
        {"timestamp":"2026-11-06T00:00:02Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Synthetic runtime bootstrap answer"}]}}
        """);
    Files.writeString(
        home.resolve(".codex/session_index.jsonl"),
        """
        {"id":"11111111-2222-4333-8444-555555555555","thread_name":"Synthetic runtime bootstrap","updated_at":"2026-11-06T00:00:02Z"}
        """);
    Path index = temporary.resolve("index");
    Path output = temporary.resolve("serve.log");
    int port;
    try (ServerSocket socket = new ServerSocket(0, 0, InetAddress.getLoopbackAddress())) {
      port = socket.getLocalPort();
    }
    List<String> command = new ArrayList<>();
    if (windows) {
      command.addAll(List.of("cmd.exe", "/d", "/c"));
    }
    command.addAll(
        List.of(
            launcher.toString(),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            Integer.toString(port),
            "--index-dir",
            index.toString()));
    ProcessBuilder builder = new ProcessBuilder(command).directory(temporary.toFile());
    // 清除继承的来源路径、JVM options 和配置；只保留 Windows 启动 shell 所需变量。
    String systemRoot = builder.environment().get("SystemRoot");
    builder.environment().clear();
    if (systemRoot != null) {
      builder.environment().put("SystemRoot", systemRoot);
    }
    builder.environment().put("PATH", windows ? systemRoot + "\\System32" : "/usr/bin:/bin");
    builder.environment().put("HOME", home.toString());
    builder.environment().put("USERPROFILE", home.toString());
    builder.environment().put("XDG_CONFIG_HOME", home.resolve("config").toString());
    builder.environment().put("XDG_DATA_HOME", home.resolve("data").toString());
    builder.environment().put("JAVA_HOME", temporary.resolve("absent-jdk").toString());
    builder.environment().put("JAVA_TOOL_OPTIONS", "-Duser.home=\"" + home + "\"");
    builder.redirectErrorStream(true).redirectOutput(output.toFile());
    Process process = builder.start();
    try {
      awaitApi(process, port, index, root, output);
      assertThat(process.isAlive()).as("正常 serve 必须保持运行").isTrue();
    } catch (Exception | AssertionError failure) {
      throw new AssertionError(
          "Isolated synthetic runtime log:\n" + Files.readString(output), failure);
    } finally {
      List<ProcessHandle> descendants = process.descendants().toList();
      descendants.forEach(ProcessHandle::destroy);
      process.destroy();
      if (!process.waitFor(10, TimeUnit.SECONDS)) {
        process.destroyForcibly();
      }
      assertThat(process.waitFor(10, TimeUnit.SECONDS)).as("测试子进程必须完成清理").isTrue();
      assertThat(process.isAlive()).isFalse();
      for (ProcessHandle child : descendants) {
        if (child.isAlive()) {
          child.destroyForcibly();
          child.onExit().get(10, TimeUnit.SECONDS);
        }
        assertThat(child.isAlive()).as("测试后代进程必须完成清理").isFalse();
      }
    }
  }

  private static void awaitApi(Process process, int port, Path index, Path root, Path output)
      throws Exception {
    try (HttpClient client =
        HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build()) {
      HttpRequest request =
          HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/sessions/summary"))
              .timeout(Duration.ofSeconds(2))
              .GET()
              .build();
      long deadline = System.nanoTime() + Duration.ofSeconds(60).toNanos();
      while (process.isAlive() && System.nanoTime() < deadline) {
        try {
          PidFile.Metadata metadata = PidFile.read(index);
          if (metadata == null) {
            Thread.sleep(100);
            continue;
          }
          assertThat(metadata.port()).isEqualTo(port);
          assertThat(metadata.indexDir()).isEqualTo(index.toAbsolutePath().normalize());
          ProcessHandle server =
              process.pid() == metadata.pid()
                  ? process.toHandle()
                  : process
                      .descendants()
                      .filter(child -> child.pid() == metadata.pid())
                      .findFirst()
                      .orElseThrow(() -> new AssertionError("PID 文件不是测试自有进程"));
          Path javaExecutable = Path.of(server.info().command().orElseThrow()).toRealPath();
          assertThat(javaExecutable.getParent().getParent())
              .isEqualTo(root.resolve("runtime").toRealPath());
          HttpResponse<String> response =
              client.send(request, HttpResponse.BodyHandlers.ofString());
          if (response.statusCode() == 200) {
            var mapper = new ObjectMapper();
            HttpRequest statusRequest =
                HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/scan-status"))
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();
            HttpResponse<String> statusResponse =
                client.send(statusRequest, HttpResponse.BodyHandlers.ofString());
            if (statusResponse.statusCode() == 200) {
              var status = mapper.readTree(statusResponse.body());
              if ("success".equals(status.path("status").asText())) {
                assertThat(status.path("processedCount").asInt(-1)).isEqualTo(1);
                assertThat(status.path("publishedProcessedCount").asInt(-1)).isEqualTo(1);
                assertThat(status.path("errorCount").asInt(-1)).isZero();
                HttpResponse<String> published =
                    client.send(request, HttpResponse.BodyHandlers.ofString());
                assertThat(published.statusCode()).isEqualTo(200);
                assertThat(mapper.readTree(published.body()).path("totalCount").asLong(-1))
                    .isEqualTo(1);
                assertThat(status.path("publishedDataAvailable").asBoolean()).isTrue();
                assertThat(index.resolve(RuntimePaths.DB_FILE_NAME)).isRegularFile();
                return;
              }
              assertThat(status.path("status").asText()).isNotEqualTo("failure");
            }
          }
        } catch (IOException ignored) {
          // Jetty 监听前允许短暂连接失败，但进程退出或超时必须失败。
        }
        Thread.sleep(100);
      }
    }
    String log = Files.readString(output);
    throw new AssertionError(
        "runtime serve 未完成 Web 初始化：alive="
            + process.isAlive()
            + ", missingNaming="
            + log.contains("javax/naming/NamingException")
            + ", missingClass="
            + log.contains("NoClassDefFoundError")
            + ", exitCode="
            + (process.isAlive() ? "running" : process.exitValue())
            + "\nIsolated synthetic runtime log:\n"
            + log);
  }
}
