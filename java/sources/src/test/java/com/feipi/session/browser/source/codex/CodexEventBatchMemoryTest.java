package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.common.JsonlReader;
import java.io.File;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexEventBatchMemoryTest {
  @TempDir Path directory;

  @Test
  void replaysLargeVisibleToolTextWithoutRetainingTheWholeTreeBatch() throws Exception {
    Path file = directory.resolve("events.jsonl");
    String chunk = "T".repeat(1024 * 1024);
    try (var writer = Files.newBufferedWriter(file)) {
      for (int index = 0; index < 80; index++) {
        writer.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool-"
                + index
                + "\",\"output\":[{\"type\":\"input_text\",\"text\":\"");
        writer.write(chunk);
        writer.write("\"}],\"unknown\":{\"text\":\"unconsumed sentinel\"}}}\r\n");
      }
    }
    var classpath = new LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof URLClassLoader urls) {
        for (var url : urls.getURLs()) classpath.add(Path.of(url.toURI()).toString());
      }
    }
    classpath.addAll(
        Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));
    Path log = directory.resolve("child.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx64m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName(),
                file.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean finished = process.waitFor(120, TimeUnit.SECONDS);
    if (!finished) process.destroyForcibly();
    assertThat(finished).isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      byte[] expected =
          MessageDigest.getInstance("SHA-256")
              .digest("T".repeat(1024 * 1024).getBytes(StandardCharsets.UTF_8));
      try (var batch = CodexEventBatch.read(new JsonlReader(), Path.of(args[0]))) {
        if (batch.events().size() != 80) throw new AssertionError("physical count");
        for (int pass = 0; pass < 2; pass++) {
          for (int index = 0; index < 80; index++) {
            var event = batch.events().get(index);
            var payload = event.path("payload");
            if (!payload.path("call_id").asText().equals("tool-" + index))
              throw new AssertionError("identity");
            String text = payload.path("output").get(0).path("text").asText();
            if (!Arrays.equals(
                expected,
                MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))))
              throw new AssertionError("text SHA");
            if (!payload.path("unknown").path("text").asText().equals("unconsumed sentinel"))
              throw new AssertionError("unknown field");
          }
        }
        if (!batch.result().diagnostics().isEmpty())
          throw new AssertionError("diagnostics changed");
      }
    }
  }
}
