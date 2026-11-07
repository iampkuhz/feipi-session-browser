package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.File;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** C7.0：直接覆盖映射后的正文驻留，不以 reader batch 成功替代验证。 */
class CodexRecordSpoolMemoryTest {
  @TempDir Path directory;
  private static final int COUNT = 96;
  private static final int LENGTH = 900_000;

  @Test
  void mappedRecordsReplayAboveHeapWithoutRetainingAllBodies() throws Exception {
    Path file = directory.resolve("synthetic-records.jsonl");
    try (var writer = Files.newBufferedWriter(file)) {
      for (int index = 0; index < COUNT; index++) {
        writer.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"");
        writer.write(body(index, LENGTH));
        writer.write("\"}]}}\n");
      }
    }
    runChild(file.toString());
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      var adapter = new CodexSourceAdapter();
      var candidate =
          new Candidate(
              adapter.fingerprint(Path.of(args[0])), "synthetic-records", "synthetic", Map.of());
      System.out.println("stage=adapter-parse count=" + COUNT);
      var result = adapter.parse(candidate, null);
      if (!(result instanceof SourceResult.Success success))
        throw new AssertionError("parse not successful");
      try (success) {
        System.out.println("stage=mapped-returned");
        if (success.candidateCount() != COUNT || success.recordSequence().recordCount() != COUNT)
          throw new AssertionError("count");
        if (!success.diagnostics().isEmpty()) throw new AssertionError("diagnostics");
        if (!success.hasManagedRecords()) throw new AssertionError("large source must be managed");
        for (int pass = 0; pass < 2; pass++) {
          try (var cursor = success.recordSequence().openCursor()) {
            for (int index = 0; index < COUNT; index++) {
              var record = cursor.next();
              if (record.eventIndex() != index
                  || !record.eventType().equals("assistant")
                  || !record.messageRole().equals(Optional.of("assistant")))
                throw new AssertionError("identity/role");
              if (!Arrays.equals(hash(body(index, LENGTH)), hash(record.content())))
                throw new AssertionError("text SHA");
              if (record.usage().total() != 0
                  || !record.usage().provenance().isEmpty()
                  || !record.toolCalls().isEmpty()
                  || record.toolUseId().isPresent()
                  || record.toolError().isPresent()) throw new AssertionError("usage/tool");
            }
          }
        }
        System.out.println("stage=verified passes=2 count=96");
      }
    }
  }

  private static String body(int index, int length) {
    String prefix = "synthetic-answer-" + index + ":";
    return prefix + "T".repeat(length - prefix.length());
  }

  private static byte[] hash(String text) throws Exception {
    return MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
  }

  private void runChild(String... arguments) throws Exception {
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
    var command =
        new java.util.ArrayList<>(
            List.of(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx64m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName()));
    command.addAll(List.of(arguments));
    Path log = directory.resolve("child.log");
    var process =
        new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log.toFile()).start();
    boolean finished = process.waitFor(180, TimeUnit.SECONDS);
    if (!finished) {
      process.destroyForcibly();
      process.waitFor(10, TimeUnit.SECONDS);
    }
    assertThat(finished).as("child timeout").isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
    assertThat(Files.readString(log)).contains("stage=verified passes=2 count=96");
  }
}
