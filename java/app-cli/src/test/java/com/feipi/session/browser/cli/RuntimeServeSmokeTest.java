package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

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
import java.util.zip.ZipFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 实际内嵌 JRE 的正常 serve 启动回归，不替代真实来源统计验收。 */
class RuntimeServeSmokeTest {
  @TempDir Path temporary;

  @Test
  void embeddedRuntimeInitializesWebWithAutomaticScanning() throws Exception {
    Path root = runtimeRoot();
    verifyPackagedSqlite(root);
    Path home = Files.createDirectory(temporary.resolve("fixture home"));
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
    ProcessBuilder builder = nativeLauncher(root, home);
    builder.redirectErrorStream(true).redirectOutput(output.toFile());
    Process process = startIsolatedServe(builder, home, index, port);
    try {
      awaitApi(process, port, index, root, output);
      assertThat(process.isAlive()).as("正常 serve 必须保持运行").isTrue();
    } catch (Exception | AssertionError failure) {
      throw new AssertionError(
          "Isolated synthetic runtime log:\n" + Files.readString(output), failure);
    } finally {
      stop(process);
    }
  }

  @Test
  void rejectsIgnoredJavaOptsBeforeServeCanScanSyntheticDefaultHome() throws Exception {
    Path home = Files.createDirectory(temporary.resolve("fixture home"));
    Path fallback = Files.createDirectory(temporary.resolve("synthetic default home"));
    Path sentinel = Files.createDirectories(fallback.resolve(".codex/sessions"));
    Files.writeString(sentinel.resolve("synthetic-home-sentinel.jsonl"), "{}\n");
    Path index = temporary.resolve("must-not-create-index");
    ProcessBuilder builder = nativeLauncher(runtimeRoot(), home);
    builder
        .redirectErrorStream(true)
        .redirectOutput(temporary.resolve("unexpected-serve.log").toFile());
    // 只用合成目录模拟 JVM 默认值；错误的 JAVA_OPTS 无法覆盖它。
    builder.environment().put("JAVA_TOOL_OPTIONS", jvmHome(fallback));
    builder.environment().put("JAVA_OPTS", jvmHome(home));
    assertThatThrownBy(() -> stop(startIsolatedServe(builder, home, index, 0)))
        .isInstanceOf(AssertionError.class)
        .hasMessage("内嵌 launcher 的 JVM user.home 未指向合成测试目录");
    assertThat(index).doesNotExist();
    assertThat(temporary.resolve("unexpected-serve.log")).doesNotExist();
  }

  private static Path runtimeRoot() {
    String distribution = System.getProperty("cli.runtime.dir");
    assertThat(distribution).as("Gradle 必须提供本轮 runtime distribution").isNotBlank();
    return Path.of(distribution).toAbsolutePath();
  }

  private ProcessBuilder nativeLauncher(Path root, Path home) {
    Path launcher = root.resolve("bin/run");
    assertThat(launcher).isRegularFile();
    assertThat(root.resolve("runtime/bin/java")).isRegularFile();
    ProcessBuilder builder = new ProcessBuilder(launcher.toString()).directory(temporary.toFile());
    // 清除继承的来源路径、JVM options 和配置。
    builder.environment().clear();
    builder.environment().put("PATH", "/usr/bin:/bin");
    builder.environment().put("HOME", home.toString());
    builder.environment().put("JAVA_HOME", temporary.resolve("absent-jdk").toString());
    builder.environment().put("JAVA_TOOL_OPTIONS", jvmHome(home));
    return builder;
  }

  private static void verifyPackagedSqlite(Path root) throws IOException {
    try (var paths = Files.list(root.resolve("app/lib"))) {
      var jars =
          paths.filter(path -> path.getFileName().toString().startsWith("sqlite-jdbc-")).toList();
      assertThat(jars).hasSize(1);
      try (var jar = new ZipFile(jars.getFirst().toFile())) {
        var entries =
            jar.stream()
                .filter(entry -> !entry.isDirectory())
                .map(entry -> entry.getName())
                .toList();
        assertThat(entries)
            .contains(
                "org/sqlite/JDBC.class",
                "META-INF/services/java.sql.Driver",
                "META-INF/maven/org.xerial/sqlite-jdbc/LICENSE");
        assertThat(entries)
            .filteredOn(name -> name.startsWith("org/sqlite/native/"))
            .containsExactly("org/sqlite/native/Mac/aarch64/libsqlitejdbc.dylib");
      }
    }
  }

  private static String jvmHome(Path home) {
    return "-Duser.home=\"" + home + "\"";
  }

  private Process startIsolatedServe(ProcessBuilder builder, Path home, Path index, int port)
      throws Exception {
    assertThat(home.getParent()).isEqualTo(temporary);
    assertThat(home).isDirectory();
    assertThat(index.getParent()).isEqualTo(temporary);
    assertThat(index).doesNotExist();
    assertThat(builder.environment()).containsEntry("HOME", home.toString());
    builder
        .command()
        .addAll(
            List.of(
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                Integer.toString(port),
                "--index-dir",
                index.toString()));
    verifyLauncherJvmHome(builder, home);
    assertThat(index).doesNotExist();
    return builder.start();
  }

  private void verifyLauncherJvmHome(ProcessBuilder launcher, Path home) throws Exception {
    List<String> command = new ArrayList<>(launcher.command());
    // 走同一个 serve launcher 分支；帮助不启动服务，另显式禁用扫描。
    command.addAll(List.of("--no-scan", "--help"));
    Path output = Files.createTempFile(temporary, "launcher-settings-", ".log");
    ProcessBuilder probe =
        new ProcessBuilder(command)
            .directory(launcher.directory())
            .redirectErrorStream(true)
            .redirectOutput(output.toFile());
    probe.environment().clear();
    probe.environment().putAll(launcher.environment());
    // 只追加显示属性的选项；保留实际启动环境中的 JVM 选项，避免探针掩盖覆盖错误。
    probe
        .environment()
        .merge(
            "JDK_JAVA_OPTIONS",
            "-XshowSettings:properties",
            (options, flag) -> options + " " + flag);
    try {
      Process process = probe.start();
      if (!process.waitFor(30, TimeUnit.SECONDS)) {
        stop(process);
        throw new AssertionError("内嵌 launcher 的无扫描预检超时");
      }
      assertThat(process.exitValue()).as("内嵌 launcher 的无扫描预检失败").isZero();
      try (var lines = Files.lines(output)) {
        boolean matches =
            lines
                .map(String::strip)
                .filter(line -> line.startsWith("user.home = "))
                .toList()
                .equals(List.of("user.home = " + home));
        assertThat(matches).withFailMessage("内嵌 launcher 的 JVM user.home 未指向合成测试目录").isTrue();
      }
    } finally {
      // JVM 属性可能带真实默认路径；探针原始输出不进入日志或报告。
      Files.deleteIfExists(output);
    }
  }

  private static void stop(Process process) throws Exception {
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
