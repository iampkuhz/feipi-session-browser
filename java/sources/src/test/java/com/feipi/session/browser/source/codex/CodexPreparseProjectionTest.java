package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderConfig;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexPreparseProjectionTest {
  @TempDir Path directory;

  @Test
  void lateImageTypeSkipsOnlyConfirmedNonTextAndPreservesRawByteRanges() throws Exception {
    String first =
        "{\"payload\":{\"output\":[{\"image_url\":\""
            + "A".repeat(4000)
            + "\",\"type\":\"input_image\"},{\"type\":\"input_text\",\"text\":\"sentinel\"}],\"call_id\":\"tool\",\"type\":\"custom_tool_call_output\"},\"type\":\"response_item\"}\r\n";
    String bad = "{bad}\n";
    Path file = Files.writeString(directory.resolve("late.jsonl"), first + bad);
    var reader = new JsonlReader(new JsonlReaderConfig(100, 500, 40));
    assertThat(reader.read(file).events()).isEmpty();
    var result = CodexEventProjection.read(reader, file);
    assertThat(result.events()).hasSize(1);
    assertThat(
            result.events().getFirst().path("payload").path("output").get(1).path("text").asText())
        .isEqualTo("sentinel");
    assertThat(result.events().getFirst().path("payload").path("call_id").asText())
        .isEqualTo("tool");
    assertThat(result.diagnostics()).noneMatch(d -> d.code().contains("BUFFER_OVERFLOW"));
    assertThat(result.diagnostics())
        .anySatisfy(
            d -> {
              assertThat(d.byteRangeStart().orElse(-1))
                  .isEqualTo(first.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
            });
    assertThat(Files.readString(file)).isEqualTo(first + bad);
  }

  @Test
  void unknownAndVisibleFieldsRemainSubjectToOriginalCap() throws Exception {
    for (String item :
        java.util.List.of(
            "{\"image_url\":\"" + "A".repeat(4000) + "\"}",
            "{\"type\":\"future_wrapper\",\"image_url\":\"" + "A".repeat(4000) + "\"}",
            "{\"type\":\"input_text\",\"text\":\"" + "A".repeat(4000) + "\"}")) {
      Path file =
          Files.writeString(
              directory.resolve("unknown.jsonl"),
              "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"content\":["
                  + item
                  + "]}}\n");
      var result =
          CodexEventProjection.read(new JsonlReader(new JsonlReaderConfig(100, 500, 40)), file);
      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).anyMatch(d -> d.code().contains("BUFFER_OVERFLOW"));
    }
  }

  @Test
  void skippedValuesStillRequireValidJsonAndUtf8() throws Exception {
    String start =
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"content\":[{\"type\":\"input_image\",\"image_url\":\""
            + "A".repeat(4000);
    Path file = directory.resolve("invalid.jsonl");
    Files.writeString(file, start + "\\q\"}]}}\n");
    var reader = new JsonlReader(new JsonlReaderConfig(100, 500, 40));
    assertThat(CodexEventProjection.read(reader, file).events()).isEmpty();
    Files.write(file, new byte[] {(byte) 0xc3, 0x28}, java.nio.file.StandardOpenOption.APPEND);
    var result = CodexEventProjection.read(reader, file);
    assertThat(result.events()).isEmpty();
    assertThat(result.diagnostics())
        .singleElement()
        .satisfies(d -> assertThat(d.code()).contains("INVALID_UTF8"));
  }

  @Test
  void multilineSnapshotsPreservePhysicalStatsAndIndependentObjects() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("multiline.jsonl"),
            "\ufeff{\"payload\":{\"replacement_history\":[\r\n{\"text\":\""
                + "A".repeat(4000)
                + "\"}\r\n],\"message\":\"visible summary\"},\"type\":\"compacted\"}"
                + "{\"type\":\"future\",\"payload\":{\"text\":\"next object\"}}\r");
    var raw = new JsonlReader().read(file);
    var result =
        CodexEventProjection.read(new JsonlReader(new JsonlReaderConfig(100, 500, 40)), file);
    assertThat(result.events()).hasSize(2);
    assertThat(result.stats()).isEqualTo(raw.stats());
    assertThat(result.events().getFirst().path("payload").path("message").asText())
        .isEqualTo("visible summary");
    assertThat(result.events().getLast()).isEqualTo(raw.events().getLast());
  }

  @Test
  void hugeImageIsBoundedInChildHeapWhilePostParseOnlyPathFails() throws Exception {
    Path file = directory.resolve("huge.jsonl");
    try (var writer = Files.newBufferedWriter(file)) {
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool\",\"output\":[{\"image_url\":\"");
      String chunk = "A".repeat(65536);
      for (int index = 0; index < 2048; index++) writer.write(chunk);
      writer.write("\",\"type\":\"input_image\"},{\"type\":\"input_text\",\"text\":\"");
      writer.write(toolText());
      writer.write(
          "\"}],\"response_id\":\"response\",\"role\":\"assistant\",\"usage\":{\"input_tokens\":3,\"output_tokens\":2}}}\n");
    }
    var classpath = new java.util.LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof java.net.URLClassLoader urls) {
        for (var url : urls.getURLs()) classpath.add(Path.of(url.toURI()).toString());
      }
    }
    classpath.addAll(
        java.util.Arrays.asList(
            System.getProperty("java.class.path").split(java.io.File.pathSeparator)));
    for (String mode : java.util.List.of("old", "new")) {
      Path log = directory.resolve(mode + ".log");
      var child =
          new ProcessBuilder(
                  Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                  "-XX:+UseSerialGC",
                  "-Xms16m",
                  "-Xmx64m",
                  "-cp",
                  String.join(java.io.File.pathSeparator, classpath),
                  HeapProbe.class.getName(),
                  file.toString(),
                  mode)
              .redirectErrorStream(true)
              .redirectOutput(log.toFile())
              .start();
      boolean done = child.waitFor(120, java.util.concurrent.TimeUnit.SECONDS);
      if (!done) child.destroyForcibly();
      assertThat(done).as(mode).isTrue();
      if (mode.equals("new")) assertThat(child.exitValue()).as(Files.readString(log)).isZero();
      else assertThat(child.exitValue()).isNotZero();
    }
  }

  @Test
  void unknownKeysCannotMasqueradeAsFixedPathsOrTypes() throws Exception {
    for (String content :
        java.util.List.of(
            "{\"type\":\"response_item\",\"payload.content\":[{\"type\":\"input_image\",\"image_url\":\""
                + "A".repeat(4000)
                + "\"}],\"payload\":{\"type\":\"message\"}}",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"content\":{\"[]\":{\"type\":\"input_image\",\"image_url\":\""
                + "A".repeat(4000)
                + "\"}}}}",
            new com.fasterxml.jackson.databind.ObjectMapper()
                .writeValueAsString(
                    java.util.Map.of(
                        "type",
                        "response_item",
                        "payload",
                        java.util.Map.of(
                            "type",
                            "message",
                            "content",
                            java.util.List.of(
                                java.util.Map.of(
                                    Character.toString(9) + "ype",
                                    "input_image",
                                    "image_url",
                                    "A".repeat(4000)))))))) {
      Path file = Files.writeString(directory.resolve("alias.jsonl"), content);
      var result =
          CodexEventProjection.read(new JsonlReader(new JsonlReaderConfig(100, 500, 40)), file);
      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).anyMatch(d -> d.code().contains("BUFFER_OVERFLOW"));
    }
  }

  private static String toolText() {
    return "before-" + "文本".repeat(32768) + "-after";
  }

  private static byte[] digest(Path path) throws Exception {
    var digest = java.security.MessageDigest.getInstance("SHA-256");
    try (var input = new java.security.DigestInputStream(Files.newInputStream(path), digest)) {
      input.transferTo(java.io.OutputStream.nullOutputStream());
    }
    return digest.digest();
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      Path file = Path.of(args[0]);
      byte[] before = digest(file);
      var result =
          args[1].equals("old")
              ? new JsonlReader().read(file, new CodexEventProjection())
              : CodexEventProjection.read(new JsonlReader(), file);
      if (result.events().size() != 1)
        throw new AssertionError("expected complete tool output, original cap rejected raw image");
      String text =
          result.events().getFirst().path("payload").path("output").get(1).path("text").asText();
      if (!java.util.Arrays.equals(
          java.security.MessageDigest.getInstance("SHA-256")
              .digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8)),
          java.security.MessageDigest.getInstance("SHA-256")
              .digest(toolText().getBytes(java.nio.charset.StandardCharsets.UTF_8))))
        throw new AssertionError("tool text SHA changed");
      if (!java.util.Arrays.equals(before, digest(file)))
        throw new AssertionError("source SHA changed");
      var payload = result.events().getFirst().path("payload");
      if (!payload.path("role").asText().equals("assistant")
          || !payload.path("response_id").asText().equals("response")
          || payload.path("usage").path("input_tokens").asInt() != 3
          || payload.path("usage").path("output_tokens").asInt() != 2)
        throw new AssertionError("usage or identity changed");
      if (!result.events().getFirst().path("payload").path("call_id").asText().equals("tool"))
        throw new AssertionError("identity changed");
      if (result.diagnostics().stream().anyMatch(d -> d.code().contains("BUFFER_OVERFLOW")))
        throw new AssertionError("projected record rejected");
    }
  }
}
