package com.feipi.session.browser.scan.engine.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 独立结构位置不按内容相等去重，完整原始事件仍然保留。 */
class ImportPayloadCatalogTest {
  @TempDir Path directory;

  @ParameterizedTest
  @ValueSource(booleans = {false, true})
  void equalContainersPreserveIndependentDeclarationsAndResultsWithoutDroppingRawEvents(
      boolean topLevelResult) throws Exception {
    var mapper = new ObjectMapper();
    var assistant = mapper.createObjectNode().put("role", "assistant");
    JsonNode declaration =
        mapper.readTree(
            """
            [{"type":"tool_use","id":"tool-1","name":"Bash","input":{"command":"echo synthetic"}}]
            """);
    var user = mapper.createObjectNode().put("role", "user");
    if (topLevelResult) user.put("type", "tool_result").put("tool_use_id", "tool-1");
    JsonNode result =
        mapper.readTree(
            """
            {"type":"tool_result","call_id":"tool-1","parts":[{"type":"text","text":"synthetic output"}]}
            """);
    mirror(assistant, declaration);
    mirror(user, result);
    String first = mapper.writeValueAsString(assistant);
    String last = mapper.writeValueAsString(user);
    Path file = directory.resolve("synthetic.jsonl");
    Files.writeString(file, first + "\n" + last);
    var catalog = ImportPayloadCatalog.read(file, "imports/synthetic/upload.jsonl");
    assertThat(catalog).hasSize(14);
    var tools =
        catalog.values().stream().filter(entry -> "tool_use".equals(entry.unitType())).toList();
    assertThat(tools).hasSize(6);
    assertThat(tools.getFirst().direction()).isEqualTo(SourceUnitDirection.RESPONSE);
    assertThat(tools.getFirst().payload()).isInstanceOf(Map.class);
    var payload = (Map<?, ?>) tools.getFirst().payload();
    assertThat(payload.get("id")).isEqualTo("tool-1");
    assertThat(payload.get("input")).isEqualTo("{\"command\":\"echo synthetic\"}");
    var results =
        catalog.values().stream().filter(entry -> "tool_result".equals(entry.unitType())).toList();
    assertThat(results).hasSize(6);
    assertThat(results.getFirst().label()).contains("tool-1");
    assertThat(results.getFirst().text()).contains("synthetic output");
    assertThat(
            catalog.values().stream()
                .filter(entry -> "import_raw_event".equals(entry.unitType()))
                .map(entry -> entry.payload())
                .toList())
        .containsExactly(first, last);
  }

  @Test
  void legalNestedDepthsPreserveCompleteStructuralCoordinates() throws Exception {
    var mapper = new ObjectMapper();
    int maximum = mapper.getFactory().streamReadConstraints().getMaxNestingDepth();
    for (String field : List.of("message", "content")) {
      for (int depth : List.of(32, 256, 512, maximum - 3)) {
        String raw =
            "{\"type\":\"response_item\","
                + ("\"" + field + "\":{").repeat(depth)
                + "\"content\":[{\"type\":\"tool_use\",\"id\":\"deep\",\"name\":\"Read\",\"input\":\"synthetic\"}]"
                + "}".repeat(depth)
                + "}";
        Path file = directory.resolve("legal-" + field + "-" + depth + ".jsonl");
        Files.writeString(file, raw + "\n");
        assertThat(mapper.readTree(raw).isObject()).isTrue();
        var validated =
            ImportInputValidator.validate(
                file,
                new com.feipi.session.browser.source.codex.CodexSourceAdapter(),
                com.feipi.session.browser.index.api.imports.ImportLimits.defaults());
        assertThat(validated.objectCount()).isEqualTo(1);
        var catalog =
            ImportPayloadCatalog.read(validated.analysisFile(), "imports/deep/upload.jsonl");
        String key =
            "imports/deep/upload.jsonl#raw[0]/tool" + ("/" + field).repeat(depth) + "/content/0";
        assertThat(catalog.keySet()).containsExactly("imports/deep/upload.jsonl#raw[0]", key);
        assertThat(catalog.get("imports/deep/upload.jsonl#raw[0]").payload()).isEqualTo(raw);
        assertThat(((Map<?, ?>) catalog.get(key).payload()).get("input")).isEqualTo("synthetic");
      }
    }
  }

  private static void mirror(ObjectNode event, JsonNode content) {
    for (ObjectNode owner :
        List.of(event, event.putObject("message"), event.putObject("payload"))) {
      owner.set("content", content);
      owner.set("parts", content);
    }
  }
}
