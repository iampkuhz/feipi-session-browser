package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderConfig;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.File;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexEventProjectionTest {
  @TempDir Path directory;

  @Test
  void defaultReaderPreservesRawImagesAndProjectionKeepsTextIdentityAndUnknownFields()
      throws Exception {
    String content =
        """
        {"type":"response_item","timestamp":"2026-11-05T10:00:00Z","payload":{"type":"custom_tool_call_output","call_id":"tool","output":[{"type":"input_image","image_url":"data:image/png;base64,AAAA"},{"type":"input_text","text":"valid tool text"},{"type":"future_wrapper","nested":{"type":"input_image","image_url":"must stay"}}],"unknown":{"text":"future content","data":"must stay"}}}
        {"type":"response_item","payload":{"type":"reasoning","encrypted_content":"opaque","summary":[{"type":"text","text":"visible summary"}],"unknown":"must stay"}}
        {"type":"event_msg","payload":{"type":"item_completed","turn_id":"turn","item":{"snapshot":"large"},"unknown":"must stay"}}
        {"type":"compacted","payload":{"message":"visible compacted summary","replacement_history":[{"role":"user","content":"historical snapshot"}],"unknown":"must stay"}}
        {"type":"future_event","payload":{"type":"future_image","image_url":"must stay","text":"future body"}}
        """;
    Path file = Files.writeString(directory.resolve("projection.jsonl"), content);
    var raw = new JsonlReader().read(file);
    assertThat(
            raw.events()
                .getFirst()
                .path("payload")
                .path("output")
                .get(0)
                .path("image_url")
                .asText())
        .isEqualTo("data:image/png;base64,AAAA");
    var projected = CodexEventProjection.read(new JsonlReader(), file);
    assertThat(projected.stats()).isEqualTo(raw.stats());
    assertThat(projected.stoppedByLimit()).isEqualTo(raw.stoppedByLimit());
    var mapper = new ObjectMapper();
    var expected = mapper.readTree("[" + content.strip().replace("}\n{", "},{") + "]");
    ((com.fasterxml.jackson.databind.node.ObjectNode)
            expected.get(0).path("payload").path("output").get(0))
        .remove("image_url");
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(1).path("payload"))
        .remove("encrypted_content");
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(2).path("payload"))
        .remove("item");
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(3).path("payload"))
        .remove("replacement_history");
    assertThat(mapper.<com.fasterxml.jackson.databind.JsonNode>valueToTree(projected.events()))
        .isEqualTo(expected);
    assertThat(Files.readString(file)).isEqualTo(content);
    assertThat(projected.diagnostics())
        .anySatisfy(
            diagnostic ->
                assertThat(diagnostic.code()).isEqualTo("CODEX_NON_TEXT_PAYLOAD_PROJECTED"));
  }

  @Test
  void confirmedImageCanProjectBeforeCapWhileDefaultReaderStillRejectsRaw() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("overflow.jsonl"),
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"content\":[{\"type\":\"input_image\",\"image_url\":\""
                + "A".repeat(300)
                + "\"}]}}\n");
    var reader = new JsonlReader(new JsonlReaderConfig(100, 200, 40));
    var raw = reader.read(file);
    var projected = CodexEventProjection.read(reader, file);
    assertThat(raw.events()).isEmpty();
    assertThat(raw.diagnostics())
        .anyMatch(diagnostic -> diagnostic.code().contains("BUFFER_OVERFLOW"));
    assertThat(projected.events()).hasSize(1);
    assertThat(projected.diagnostics())
        .noneMatch(diagnostic -> diagnostic.code().contains("BUFFER_OVERFLOW"));
  }

  @Test
  void manyLargeImagePayloadsKeepQuestionToolTextUsageAndLocatorsWithinBoundedHeap()
      throws Exception {
    Path root = Files.createDirectories(directory.resolve("codex"));
    Files.writeString(root.resolve("session_index.jsonl"), "{\"id\":\"bounded\"}\n");
    Path rollout =
        Files.createDirectories(root.resolve("sessions")).resolve("rollout-bounded.jsonl");
    String image = "A".repeat(1024 * 1024);
    try (var writer = Files.newBufferedWriter(rollout)) {
      writer.write("{\"type\":\"session_meta\",\"payload\":{\"id\":\"bounded\"}}\n");
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":\"bounded"
              + " prompt\"}}\n");
      for (int index = 0; index < 72; index++) {
        writer.write(
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\"tool-"
                + index
                + "\",\"name\":\"synthetic\",\"input\":\"keep input\"}}\n");
        writer.write(
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool-"
                + index
                + "\",\"output\":[{\"type\":\"input_image\",\"image_url\":\"data:image/png;base64,"
                + image
                + "\"},{\"type\":\"input_text\",\"text\":\"tool text "
                + index
                + "\"}]}}\n");
      }
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\"bounded"
              + " answer\"}}\n");
      writer.write(
          "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"bounded-response\",\"usage\":{\"input_tokens\":10,\"output_tokens\":3}}}\n");
    }
    var classpath = new LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof URLClassLoader urls) {
        for (var url : urls.getURLs()) {
          if ("file".equals(url.getProtocol())) classpath.add(Path.of(url.toURI()).toString());
        }
      }
    }
    classpath.addAll(
        Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));
    Path log = directory.resolve("bounded-heap.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx64m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName(),
                root.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean finished = process.waitFor(90, TimeUnit.SECONDS);
    if (!finished) process.destroyForcibly();
    assertThat(finished).as("bounded heap probe completion").isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      var adapter = new CodexSourceAdapter();
      var candidates = adapter.discover(Path.of(args[0])).orderedItems();
      if (candidates.size() != 1) throw new AssertionError("candidate count");
      var candidate = candidates.getFirst();
      var before = adapter.fingerprint(Path.of(candidate.fingerprint().locator()));
      var parsed = (SourceResult.Success) adapter.parse(candidate, null);
      String bodies =
          parsed.records().stream()
              .map(record -> record.content())
              .collect(Collectors.joining("\n"));
      if (!bodies.contains("bounded prompt")
          || !bodies.contains("bounded answer")
          || !bodies.contains("tool text 0")
          || !bodies.contains("tool text 71")) throw new AssertionError("text lost");
      if (parsed.records().stream().mapToLong(record -> record.usage().total()).sum() != 13)
        throw new AssertionError("usage changed");
      if (parsed.candidateCount() != 148 || parsed.records().size() != 148)
        throw new AssertionError("physical count changed");
      for (var record : parsed.records()) {
        if (!record
            .locator()
            .equals(candidate.fingerprint().locator() + "#event[" + record.eventIndex() + "]"))
          throw new AssertionError("locator changed");
      }
      if (!before.equals(adapter.fingerprint(Path.of(candidate.fingerprint().locator()))))
        throw new AssertionError("source modified");
    }
  }
}
