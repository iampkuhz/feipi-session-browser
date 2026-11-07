package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.SourceResult;
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

class CodexParseMemoryTest {
  private static final int TOOLS = 192;
  private static final String TEXT_PART = "T".repeat(65_536);
  private static final String INPUT_TEXT = "I".repeat(16_384);
  @TempDir Path directory;

  @Test
  void onlyConsumedToolFieldsAreReleasedFromSharedEventNodes() throws Exception {
    var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
    var original =
        mapper.readTree(
            """
            [
              {"type":"response_item","payload":{"type":"message","role":"user","content":"prompt"}},
              {"type":"response_item","payload":{"type":"function_call","call_id":"f","name":"synthetic","arguments":{"value":"f input"},"input":"unconsumed stays"}},
              {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"c","name":"synthetic","input":{"value":"c input"},"arguments":"unconsumed stays"}},
              {"type":"response_item","payload":{"type":"custom_tool_call_output","call_id":"c","output":[{"type":"input_text","text":"tool output"}],"unknown":"must stay"}},
              {"type":"response_item","payload":{"type":"message","role":"assistant","content":"answer"}},
              {"type":"token_usage_record","payload":{"response_id":"r","usage":{"input_tokens":10,"output_tokens":3}}},
              {"type":"future_event","payload":{"input":"unknown input","output":"unknown output","arguments":"unknown arguments"}},
              {"type":"event_msg","payload":{"type":"agent_message","message":"distinct final"}}
            ]
            """);
    var events = new java.util.ArrayList<com.fasterxml.jackson.databind.JsonNode>();
    original.forEach(node -> events.add(node.deepCopy()));
    var expected = original.deepCopy();
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(1).path("payload"))
        .remove("arguments");
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(2).path("payload"))
        .remove("input");
    ((com.fasterxml.jackson.databind.node.ObjectNode) expected.get(3).path("payload"))
        .remove("output");
    Class<?> stateClass = Class.forName(CodexSourceAdapter.class.getName() + "$CodexParseState");
    var stateConstructor =
        stateClass.getDeclaredConstructor(
            String.class,
            String.class,
            com.feipi.session.browser.source.spi.SourceAdapter.CancellationSignal.class);
    stateConstructor.setAccessible(true);
    Object state = stateConstructor.newInstance("synthetic", "synthetic-model", null);
    var method =
        CodexSourceAdapter.class.getDeclaredMethod(
            "appendParsedEvents",
            CodexActivityRange.class,
            stateClass,
            com.feipi.session.browser.domain.source.SourceRecordRelation.class,
            java.util.Map.class,
            java.util.List.class,
            CodexRecordSpool.class);
    method.setAccessible(true);
    try (var records = new CodexRecordSpool()) {
      method.invoke(
          null,
          CodexActivityRange.create(events, java.util.List.of()),
          state,
          com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
          java.util.Map.of(),
          new java.util.ArrayList<>(),
          records);
      records.seal();
      assertThat(mapper.<com.fasterxml.jackson.databind.JsonNode>valueToTree(events))
          .isEqualTo(expected);
      assertThat(records.stream().map(record -> record.content()))
          .contains("prompt", "answer", "tool output", "distinct final");
    }
  }

  @Test
  void mappedToolTreesAreReleasedWithoutChangingAnyInputOutputHash() throws Exception {
    Path root = Files.createDirectories(directory.resolve("codex"));
    Files.writeString(root.resolve("session_index.jsonl"), "{\"id\":\"text-memory\"}\n");
    Path rollout =
        Files.createDirectories(root.resolve("sessions")).resolve("rollout-text-memory.jsonl");
    try (var writer = Files.newBufferedWriter(rollout)) {
      writer.write("{\"type\":\"session_meta\",\"payload\":{\"id\":\"text-memory\"}}\n");
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":\"memory"
              + " prompt\"}}\n");
      for (int tool = 0; tool < TOOLS; tool++) {
        writer.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-11-05T10:00:00Z\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\"tool-"
                + tool
                + "\",\"name\":\"synthetic\",\"input\":"
                + input()
                + "}}\n");
        writer.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-11-05T10:00:01Z\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool-"
                + tool
                + "\",\"output\":[");
        for (int part = 0; part < 4; part++) {
          if (part > 0) writer.write(",");
          writer.write("{\"type\":\"input_text\",\"text\":\"" + text(tool, part) + "\"}");
        }
        writer.write(
            "]" + (tool == 0 ? ",\"error\":{\"message\":\"synthetic error\"}" : "") + "}}\n");
      }
      writer.write(
          "{\"type\":\"future_event\",\"payload\":{\"content\":\"unknown content remains"
              + " raw\"}}\n");
      writer.write(
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\"memory"
              + " answer\"}}\n");
      writer.write(
          "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"memory-response\",\"usage\":{\"input_tokens\":10,\"output_tokens\":3}}}\n");
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
    Path log = directory.resolve("text-memory.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx96m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName(),
                root.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean completed = process.waitFor(90, TimeUnit.SECONDS);
    if (!completed) process.destroyForcibly();
    assertThat(completed).as("tool text heap probe completion").isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
  }

  private static String input() {
    return "{\"text\":\"" + INPUT_TEXT + "\",\"meta\":\"keep\"}";
  }

  private static String text(int tool, int part) {
    return "tool-" + tool + "-part-" + part + ":" + TEXT_PART;
  }

  private static byte[] hash(String content) throws Exception {
    return MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8));
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      var adapter = new CodexSourceAdapter();
      var candidate = adapter.discover(Path.of(args[0])).orderedItems().getFirst();
      var before = candidate.fingerprint();
      var parsed = (SourceResult.Success) adapter.parse(candidate, null);
      try (parsed) {
        int inputs = 0;
        int outputs = 0;
        boolean prompt = false;
        boolean answer = false;
        long totalUsage = 0;
        try (var cursor = parsed.recordSequence().openCursor()) {
          while (cursor.hasNext()) {
            var record = cursor.next();
            totalUsage += record.usage().total();
            if ("tool_result".equals(record.eventType())) {
              int tool =
                  Integer.parseInt(record.toolUseId().orElseThrow().substring("tool-".length()));
              var expected = new StringBuilder();
              for (int part = 0; part < 4; part++) expected.append(text(tool, part));
              if (!Arrays.equals(hash(record.content()), hash(expected.toString())))
                throw new AssertionError("tool output hash changed");
              if (tool == 0 && !record.toolError().orElse("").equals("synthetic error"))
                throw new AssertionError("tool error lost");
              outputs++;
            }
            for (var tool : record.toolCalls()) {
              if (!Arrays.equals(hash(tool.input()), hash(input())))
                throw new AssertionError("tool input hash changed");
              inputs++;
            }
            prompt |=
                "memory prompt".equals(record.content())
                    && record.messageRole().orElse("").equals("user");
            answer |=
                "memory answer".equals(record.content())
                    && record.messageRole().orElse("").equals("assistant");
            if (!record.locator().equals(before.locator() + "#event[" + record.eventIndex() + "]"))
              throw new AssertionError("locator changed");
          }
        }
        if (inputs != TOOLS || outputs != TOOLS || !prompt || !answer)
          throw new AssertionError("content count changed");
        if (totalUsage != 13) throw new AssertionError("usage changed");
        if (parsed.candidateCount() != TOOLS * 2 + 5
            || parsed.recordSequence().recordCount() != TOOLS * 2 + 5)
          throw new AssertionError("physical count changed");
        if (!before.equals(adapter.fingerprint(Path.of(before.locator()))))
          throw new AssertionError("raw source changed");
      }
    }
  }
}
