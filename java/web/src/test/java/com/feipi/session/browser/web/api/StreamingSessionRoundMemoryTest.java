package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 固定堆验证少调用大正文的元数据窗口，不把计数上限当作正文内存预算。 */
class StreamingSessionRoundMemoryTest {
  @TempDir Path directory;

  @Test
  void metadataWindowDoesNotRetain96LargeCallBodies() throws Exception {
    Path data = directory.resolve("content.json");
    writeFixture(data);
    var entries = new LinkedHashSet<String>();
    entries.add(System.getProperty("java.class.path"));
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof java.net.URLClassLoader urls) {
        for (var url : urls.getURLs()) entries.add(Path.of(url.toURI()).toString());
      }
    }
    Path log = directory.resolve("consumer-64m.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-Xmx64m",
                "-cp",
                String.join(java.io.File.pathSeparator, entries),
                Probe.class.getName(),
                data.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean done = process.waitFor(120, TimeUnit.SECONDS);
    if (!done) process.destroyForcibly();
    assertThat(done).withFailMessage("64MiB consumer exceeded test deadline").isTrue();
    assertThat(process.exitValue()).withFailMessage(Files.readString(log)).isZero();
    assertThat(Files.readString(log)).contains("CONSUMER_REPLAY_OK calls=96 payloads=192");
  }

  private static void writeFixture(Path data) throws Exception {
    try (var writer = Files.newBufferedWriter(data)) {
      writer.write(
          "{\"storageFormat\":\"session-content.units.v1\",\"header\":{"
              + "\"schemaVersion\":\"session-detail.normalized.v3\",\"agent\":\"codex\","
              + "\"session\":{\"session_key\":\"codex:synthetic\"},\"totals\":{\"calls\":96,"
              + "\"toolExecutions\":0,\"diagnostics\":0,\"sourceFiles\":0,"
              + "\"sourceUnitCatalog\":0,\"sourceUnitSequenceEntries\":0}},\"units\":[");
      for (int n = 0; n < 96; n++) {
        if (n > 0) writer.write(",");
        writer.write(
            "{\"unitIndex\":"
                + n
                + ",\"calls\":[{\"call_id\":\"c"
                + n
                + "\",\"call_index\":"
                + (n + 1)
                + ",\"turn_id\":\"shared-turn\","
                + "\"source_units\":[{\"role\":\"assistant\",\"text\":\"");
        writer.write(text(n));
        writer.write("\"}]}]}");
      }
      writer.write("]}");
    }
    var digest = MessageDigest.getInstance("SHA-256");
    try (var input = Files.newInputStream(data)) {
      byte[] buffer = new byte[8192];
      int read;
      while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
    }
    Files.writeString(
        data.resolveSibling("content.meta.json"),
        "{\"contentHash\":\""
            + HexFormat.of().formatHex(digest.digest())
            + "\",\"contentSize\":"
            + Files.size(data)
            + "}");
  }

  private static String text(int n) {
    String prefix = "synthetic-" + n + ":";
    return prefix + "x".repeat(900000 - prefix.length());
  }

  private static String sha(String text) throws Exception {
    return HexFormat.of()
        .formatHex(
            MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
  }

  /** 子进程只保留元数据结果，单项正文读取后立即核对摘要并释放。 */
  public static final class Probe {
    /** 以固定堆预算重放同一内容的两遍元数据窗口和首尾完整载荷。 */
    public static void main(String[] args) throws Exception {
      var content = NormalizedArtifactLoader.open(Path.of(args[0]));
      var original = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
      var detail =
          new com.feipi.session.browser.application.sessiondetail.SessionDetail(
              original.sessionRow(),
              java.util.List.of(),
              java.util.List.of(),
              original.visibility(),
              args[0],
              content.header().schemaVersion(),
              "consumer-fixture-v1",
              1,
              192);
      var service =
          new SessionApiService(
              (key, visibility) ->
                  java.util.Optional.of(
                      new com.feipi.session.browser.application.SessionDetailUseCase.DetailContext(
                          detail, null, content)));
      var members = new SessionApiHandler(service);
      var annotated =
          new com.feipi.session.browser.application.SessionDetailUseCase.AnnotatedDetailContext(
              detail,
              com.feipi.session.browser.query.api.SessionAnomalySummary.empty(
                  detail.sessionRow().sessionKey()),
              null,
              content);
      var details =
          new SessionDetailApiHandler(
              ctx ->
                  new SessionDetailApiHandler.LoadedDetail(
                      new SessionDetailApiResponses.SessionDetailFilterEcho(
                          "codex", "health", "full", "", ""),
                      annotated,
                      "/synthetic",
                      false));
      var app =
          io.javalin.Javalin.create(
                  config -> {
                    config.routes.get(
                        "/round/1", ctx -> members.handleRound(ctx, "codex", "health", 1));
                    config.routes.get("/metrics", details::handleMetrics);
                    config.routes.get("/payloads", details::handlePayloads);
                    config.routes.get(
                        "/first",
                        ctx -> members.handlePayload(ctx, "codex", "health", "main:resp:c0"));
                    config.routes.get(
                        "/last",
                        ctx -> members.handlePayload(ctx, "codex", "health", "main:resp:c95"));
                  })
              .start("127.0.0.1", 0);
      try {
        var proxy =
            new java.net.ProxySelector() {
              public java.util.List<java.net.Proxy> select(java.net.URI uri) {
                return java.util.List.of(java.net.Proxy.NO_PROXY);
              }

              public void connectFailed(
                  java.net.URI uri, java.net.SocketAddress address, java.io.IOException error) {}
            };
        var client = java.net.http.HttpClient.newBuilder().proxy(proxy).build();
        var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        for (int replay = 0; replay < 2; replay++) {
          var round = get(client, mapper, app.port(), "/round/1?limit=500");
          if (round.path("total").asInt() != 96
              || !round.path("nextCursor").isNull()
              || round.at("/round/calls").size() != 96
              || !round.at("/round/calls/0/callId").asText().equals("c0")
              || !round.at("/round/calls/95/callId").asText().equals("c95")) {
            throw new AssertionError("HTTP round metadata incomplete: " + round);
          }
          var metrics = get(client, mapper, app.port(), "/metrics");
          if (metrics.path("roundCount").asInt() != 1
              || metrics.path("payloadCount").asInt() != 192) {
            throw new AssertionError("HTTP detail totals changed");
          }
          var payloads = get(client, mapper, app.port(), "/payloads?limit=500");
          if (payloads.path("total").asInt() != 192
              || payloads.path("payloads").size() != 192
              || !payloads.path("nextCursor").isNull()) {
            throw new AssertionError("HTTP payload metadata incomplete");
          }
          for (int n : new int[] {0, 95}) {
            var payload = get(client, mapper, app.port(), n == 0 ? "/first" : "/last");
            if (!sha(payload.path("content").asText()).equals(sha(text(n)))) {
              throw new AssertionError("HTTP payload SHA changed");
            }
          }
        }
      } finally {
        app.stop();
      }
      System.out.println("CONSUMER_REPLAY_OK calls=96 payloads=192");
    }

    private static com.fasterxml.jackson.databind.JsonNode get(
        java.net.http.HttpClient client,
        com.fasterxml.jackson.databind.ObjectMapper mapper,
        int port,
        String route)
        throws Exception {
      var request =
          java.net.http.HttpRequest.newBuilder(
                  java.net.URI.create("http://127.0.0.1:" + port + route))
              .GET()
              .build();
      var response = client.send(request, java.net.http.HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() != 200)
        throw new AssertionError("HTTP " + response.statusCode() + " " + route);
      return mapper.readTree(response.body());
    }
  }
}
