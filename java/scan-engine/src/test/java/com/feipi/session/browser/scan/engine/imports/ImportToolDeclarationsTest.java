package com.feipi.session.browser.scan.engine.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 输入回填只使用既有明确绑定，不靠文件顺序或邻近调用猜测归属。 */
class ImportToolDeclarationsTest {
  @TempDir Path directory;

  @Test
  void restoresExplicitBindingPreservingExistingOrderUsageAndOtherCalls() throws Exception {
    var first =
        call(
            "first",
            1,
            List.of("existing", "tool-1", "existing"),
            List.of(Map.of("type", "tool_use", "role", "assistant", "id", "tool-1", "input", "")));
    var second = call("second", 2, List.of(), List.of());
    var restored =
        ImportToolDeclarations.restore(
            List.of(first, second),
            List.of(tool("tool-2", "first"), tool("tool-1", "first")),
            catalog());
    assertThat(restored).hasSize(2);
    assertThat(restored.getFirst().callId()).isEqualTo(first.callId());
    assertThat(restored.getFirst().usage()).isSameAs(first.usage());
    assertThat(restored.getFirst().request()).isSameAs(first.request());
    assertThat(restored.getFirst().response().toolCallIds())
        .containsExactly("existing", "tool-1", "existing", "tool-2");
    assertThat(restored.getFirst().sourceUnits()).hasSize(2);
    assertThat(restored.getFirst().sourceUnits().getFirst().get("input"))
        .isEqualTo("{\"command\":\"one\"}");
    assertThat(restored.getFirst().sourceUnits().getLast().get("input"))
        .isEqualTo("{\"command\":\"two\"}");
    assertThat(first.sourceUnits().getFirst().get("input")).isEqualTo("");
    assertThat(restored.getLast()).isSameAs(second);
  }

  @Test
  void declarationsWithoutKnownCallBindingCannotInventResponseReferences() throws Exception {
    var first = call("first", 1, List.of(), List.of());
    var second = call("second", 2, List.of(), List.of());
    for (List<NormalizedToolExecution> tools :
        List.of(List.<NormalizedToolExecution>of(), List.of(tool("tool-1", "unknown-call")))) {
      var restored = ImportToolDeclarations.restore(List.of(first, second), tools, catalog());
      assertThat(restored).hasSize(2);
      assertThat(restored.getFirst()).isSameAs(first);
      assertThat(restored.getLast()).isSameAs(second);
      assertThat(restored)
          .allSatisfy(
              call -> {
                assertThat(call.response().toolCallIds()).isEmpty();
                assertThat(call.sourceUnits()).isEmpty();
              });
    }
  }

  private Map<String, SourceUnitCatalogEntry> catalog() throws Exception {
    Path file = directory.resolve("synthetic.jsonl");
    Files.writeString(
        file,
        """
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"tool-1","name":"Bash","input":{"command":"one"}},{"type":"tool_use","id":"tool-2","name":"Bash","input":{"command":"two"}}]}}
        """);
    return ImportPayloadCatalog.read(file, "imports/synthetic/upload.jsonl");
  }

  private static NormalizedToolExecution tool(String id, String callId) {
    return new NormalizedToolExecution(
        id,
        "Bash",
        CallScope.MAIN,
        callId,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        0,
        List.of(),
        Optional.empty());
  }

  private static NormalizedCall call(
      String id, int index, List<String> responseIds, List<Map<String, Object>> units) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(12, 4, 3, 5, 24),
        NormalizedCallRequest.empty(),
        new NormalizedCallResponse(responseIds),
        List.of(),
        units,
        Map.of(),
        Map.of());
  }
}
