package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 固定堆验证少调用大正文的元数据窗口，不把计数上限当作正文内存预算。 */
class StreamingSessionConsumerMemoryTest {
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
      var reader = new SessionContentReader(content, 1);
      if (reader.roundIndex().roundCount() != 1) throw new AssertionError("round identity lost");
      for (int replay = 0; replay < 2; replay++) {
        var metadata = metadataWindow(reader);
        if (metadata.total() != 96
            || metadata.nextCursor() != null
            || metadata.items().size() != 96
            || !metadata.items().getFirst().equals("c0")
            || !metadata.items().getLast().equals("c95")) {
          throw new AssertionError("metadata page incomplete");
        }
        var payloads = reader.payloadSources(PayloadVisibility.FULL, 0, 500);
        if (payloads.total() != 192
            || payloads.nextCursor() != null
            || payloads.items().size() != 192
            || !payloads.items().getLast().payloadId().equals("main:resp:c95")) {
          throw new AssertionError("payload metadata incomplete");
        }
        for (int n : new int[] {0, 95}) {
          String actual =
              reader.payload("main:resp:c" + n, PayloadVisibility.FULL).orElseThrow().content();
          if (!sha(actual).equals(sha(text(n)))) throw new AssertionError("payload SHA changed");
        }
      }
      System.out.println("CONSUMER_REPLAY_OK calls=96 payloads=192");
    }

    private static SessionContentReader.Window<String> metadataWindow(SessionContentReader reader)
        throws Exception {
      return reader.calls(1, 0, 500, NormalizedCall::callId);
    }
  }
}
