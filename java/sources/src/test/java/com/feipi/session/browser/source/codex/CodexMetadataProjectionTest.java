package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.common.JsonlReader;
import java.io.File;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexMetadataProjectionTest {
  @TempDir Path directory;

  @Test
  void usageSelectionAndBothSpawnOrdersKeepExactEvidence() throws Exception {
    var mapper = new ObjectMapper();
    var events = new ArrayList<JsonNode>();
    for (String line :
        List.of(
            "{\"type\":\"turn_context\",\"payload\":{\"turn_id\":\"t\"}}",
            "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"r\",\"turn_id\":\"t\",\"usage\":{\"input_tokens\":10,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":3},\"thread_token_usage\":{\"input_tokens\":10,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":3}}}",
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":10,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":3}}}}",
            "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"reset\",\"turn_id\":\"t\",\"usage\":{\"input_tokens\":1,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":1},\"thread_token_usage\":{\"input_tokens\":1,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":1}}}",
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"last_token_usage\":{\"input_tokens\":2}}}}")) {
      events.add(mapper.readTree(line));
    }
    for (boolean reverse : List.of(false, true)) {
      JsonNode call =
          mapper.readTree(
              "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"spawn\",\"name\":\"spawn_agent\",\"arguments\":\"unused\"}}");
      JsonNode output =
          mapper.readTree(
              "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"spawn\",\"output\":\"{\\\"agent_id\\\":\\\"child\\\",\\\"task_name\\\":\\\"task\\\"}\"}}");
      var raw = new ArrayList<>(events);
      raw.addAll(reverse ? List.of(output, call) : List.of(call, output));
      var projected = raw.stream().map(CodexMetadataProjection::project).toList();
      var expected = new CodexTokenProvenance();
      var actual = new CodexTokenProvenance();
      var usage =
          CodexSourceAdapter.class.getDeclaredMethod(
              "appendTokenProvenance", List.class, CodexTokenProvenance.class);
      usage.setAccessible(true);
      usage.invoke(null, raw, expected);
      usage.invoke(null, projected, actual);
      assertThat(actual.metadata()).isEqualTo(expected.metadata());
      Class<?> selection =
          Class.forName(CodexSourceAdapter.class.getName() + "$CodexUsageSelection");
      var constructor = selection.getDeclaredConstructor(List.class);
      constructor.setAccessible(true);
      Object rawSelection = constructor.newInstance(raw);
      Object projectedSelection = constructor.newInstance(projected);
      for (String name :
          List.of("usageIndices", "resetEvents", "ambiguousEvents", "legacyDeltas")) {
        var field = selection.getDeclaredField(name);
        field.setAccessible(true);
        assertThat(field.get(projectedSelection)).as(name).isEqualTo(field.get(rawSelection));
      }

      var spawn =
          CodexSourceAdapter.class.getDeclaredMethod(
              "spawnRelations", List.class, List.class, List.class, String.class);
      spawn.setAccessible(true);
      assertThat(spawn.invoke(null, projected, List.of(), new ArrayList<>(), "synthetic"))
          .isEqualTo(spawn.invoke(null, raw, List.of(), new ArrayList<>(), "synthetic"));
    }
    Path file = directory.resolve("raw.jsonl");
    Files.writeString(file, "{\"type\":\"future\",\"payload\":{\"text\":\"keep raw\"}}\ninvalid\n");
    var raw = new JsonlReader().read(file);
    var projected = CodexMetadataProjection.read(new JsonlReader(), file);
    assertThat(projected.stats()).isEqualTo(raw.stats());
    assertThat(projected.diagnostics()).isEqualTo(raw.diagnostics());
    assertThat(Files.readString(file)).contains("keep raw");
    assertThat(raw.events().getFirst().path("payload").path("text").asText()).isEqualTo("keep raw");
  }

  @Test
  void discoveryDoesNotRetainLargeBodyAtOrdinaryHeap() throws Exception {
    Path root = Files.createDirectories(directory.resolve("codex"));
    Files.writeString(root.resolve("session_index.jsonl"), "{\"id\":\"metadata-memory\"}\n");
    Path file =
        Files.createDirectories(root.resolve("sessions")).resolve("rollout-metadata-memory.jsonl");
    try (var writer = Files.newBufferedWriter(file)) {
      writer.write("{\"type\":\"session_meta\",\"payload\":{\"id\":\"metadata-memory\"}}\n");
      String text = "T".repeat(1_048_576);
      for (int i = 0; i < 160; i++) {
        writer.write(
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\""
                + text
                + "\"}}\n");
      }
      for (int i = 0; i < 86_276; i++) {
        writer.write(
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"item_completed\",\"item\":{\"text\":\"not metadata\"}}}\n");
      }
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\"");
      String unicode = "界".repeat(100_000);
      for (int i = 0; i < 98; i++) writer.write(unicode);
      writer.write("\"}}\n");
      writer.write(
          "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"r\",\"usage\":{\"input_tokens\":10,\"cache_read_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":3}}}\n");
    }
    var classpath = new LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof URLClassLoader urls) {
        for (var url : urls.getURLs())
          if ("file".equals(url.getProtocol())) classpath.add(Path.of(url.toURI()).toString());
      }
    }
    classpath.addAll(
        Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));
    Path log = directory.resolve("metadata-memory.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx128m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName(),
                root.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean completed = process.waitFor(90, TimeUnit.SECONDS);
    if (!completed) process.destroyForcibly();
    assertThat(completed).isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      var candidate = new CodexSourceAdapter().discover(Path.of(args[0])).orderedItems();
      if (candidate.size() != 1
          || !"provider_reported"
              .equals(candidate.getFirst().metadata().get("freshInputTokenPrecision"))
          || !"provider_reported"
              .equals(candidate.getFirst().metadata().get("cacheReadTokenPrecision")))
        throw new AssertionError("metadata discovery changed");
      Path source = Path.of(args[0]).resolve("sessions/rollout-metadata-memory.jsonl");
      var events = CodexMetadataProjection.read(new JsonlReader(), source).events();
      if (events.size() != 86_439
          || !events.getLast().path("type").asText().equals("token_usage_record"))
        throw new AssertionError("physical event positions changed");
      var digest = java.security.MessageDigest.getInstance("SHA-256");
      try (var input = Files.newInputStream(source);
          var output =
              new java.security.DigestOutputStream(
                  java.io.OutputStream.nullOutputStream(), digest)) {
        input.transferTo(output);
      }
      if (!candidate
          .getFirst()
          .fingerprint()
          .contentHash()
          .orElseThrow()
          .equals(java.util.HexFormat.of().formatHex(digest.digest())))
        throw new AssertionError("raw source SHA changed");
    }
  }
}
