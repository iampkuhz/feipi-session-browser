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

/** 镜像容器只生成一份工具投影，原始事件仍完整保留。 */
class ImportPayloadCatalogTest {
  @TempDir Path directory;

  @Test
  void mirroredContainersDeduplicateDeclarationsAndObjectResultsWithoutDroppingRawEvents()
      throws Exception {
    var mapper = new ObjectMapper();
    var assistant = mapper.createObjectNode().put("role", "assistant");
    JsonNode declaration =
        mapper.readTree(
            """
            [{"type":"tool_use","id":"tool-1","name":"Bash","input":{"command":"echo synthetic"}}]
            """);
    var user = mapper.createObjectNode().put("role", "user");
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
    assertThat(catalog).hasSize(4);
    var tools =
        catalog.values().stream().filter(entry -> "tool_use".equals(entry.unitType())).toList();
    assertThat(tools).hasSize(1);
    assertThat(tools.getFirst().direction()).isEqualTo(SourceUnitDirection.RESPONSE);
    assertThat(tools.getFirst().payload()).isInstanceOf(Map.class);
    var payload = (Map<?, ?>) tools.getFirst().payload();
    assertThat(payload.get("id")).isEqualTo("tool-1");
    assertThat(payload.get("input")).isEqualTo("{\"command\":\"echo synthetic\"}");
    var results =
        catalog.values().stream().filter(entry -> "tool_result".equals(entry.unitType())).toList();
    assertThat(results).hasSize(1);
    assertThat(results.getFirst().label()).contains("tool-1");
    assertThat(results.getFirst().text()).contains("synthetic output");
    assertThat(
            catalog.values().stream()
                .filter(entry -> "import_raw_event".equals(entry.unitType()))
                .map(entry -> entry.payload())
                .toList())
        .containsExactly(first, last);
  }

  private static void mirror(ObjectNode event, JsonNode content) {
    for (ObjectNode owner :
        List.of(event, event.putObject("message"), event.putObject("payload"))) {
      owner.set("content", content);
      owner.set("parts", content);
    }
  }
}
