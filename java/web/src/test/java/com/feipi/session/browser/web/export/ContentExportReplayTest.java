package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/** 合成目录、序列和工具回归使用解码计数，避免依赖耗时。 */
class ContentExportReplayTest {
  @Test
  void catalogSequenceAndToolReplayUsesFixedPassesAtBothScales() throws Exception {
    var small = fixture(100);
    var large = fixture(200);
    export(small);
    export(large);
    System.out.println("EXPORT_REPLAY items=100 opens=" + small.opens + " reads=" + small.reads);
    System.out.println("EXPORT_REPLAY items=200 opens=" + large.opens + " reads=" + large.reads);
    assertThat(small.opens).as("100-call cursor passes").isLessThanOrEqualTo(8);
    assertThat(large.opens).as("200-call cursor passes").isLessThanOrEqualTo(8);
    assertThat(small.reads).isLessThanOrEqualTo(8 * small.units.size());
    assertThat(large.reads).isLessThanOrEqualTo(8 * large.units.size());
    assertThat(large.reads).isLessThanOrEqualTo(2 * small.reads + 8);
  }

  @Test
  void everyCatalogOccurrenceAndCallAndToolIdentityKeepsExactOrder() throws Exception {
    var content = fixture(100);
    String html = export(content);
    var calls =
        Pattern.compile(" · (call-\\d+) · tokens")
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .toList();
    assertThat(calls)
        .containsExactlyElementsOf(
            java.util.stream.IntStream.range(0, 100).mapToObj(i -> "call-" + i).toList());
    var bodies =
        Pattern.compile("BODY-\\d+-END")
            .matcher(html)
            .results()
            .map(java.util.regex.MatchResult::group)
            .toList();
    var expected = new ArrayList<String>();
    for (int i = 0; i < 100; i++) {
      expected.add("BODY-" + i + "-END");
      expected.add("BODY-" + i + "-END");
    }
    assertThat(bodies).containsExactlyElementsOf(expected);
    var tools =
        Pattern.compile("<summary>Tool (tool-\\d+) ·")
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .toList();
    assertThat(tools)
        .containsExactlyElementsOf(
            java.util.stream.IntStream.range(0, 100).mapToObj(i -> "tool-" + i).toList());
    for (int i = 0; i < 100; i++) {
      assertThat(Pattern.compile("RESULT-" + i + "-END").matcher(html).results().count())
          .as("tool result occurrence %s", i)
          .isEqualTo(1);
      assertThat(Pattern.compile("INPUT-" + i + "-END").matcher(html).results().count())
          .as("call response and tool input occurrence %s", i)
          .isEqualTo(2);
    }
  }

  @Test
  void bulkPayloadsMatchExistingSingleItemReaderForEveryFixtureIdentity() throws Exception {
    var content = fixture(4);
    var reader =
        new com.feipi.session.browser.application.sessiondetail.SessionContentReader(content, 1);
    try (var bulk = reader.exportPayloads()) {
      for (var unit : content.units) {
        for (var call : unit.calls()) {
          for (boolean request : new boolean[] {true, false}) {
            assertThat(bulk.payload(call, request, PayloadVisibility.STANDARD))
                .isEqualTo(reader.payload(call, request, PayloadVisibility.STANDARD));
          }
        }
        for (var tool : unit.toolExecutions()) {
          for (String kind : List.of("input", "result")) {
            String id = "tool:" + kind + ":" + tool.toolCallId();
            assertThat(bulk.payload(id, PayloadVisibility.STANDARD))
                .isEqualTo(reader.payload(id, PayloadVisibility.STANDARD));
          }
        }
      }
    }
  }

  @Test
  void firstCatalogAndToolInputButGlobalInlineResultPriorityMatchSingleReader() throws Exception {
    var original = fixture(2);
    var units = new ArrayList<>(original.units);
    var late =
        new NormalizedCall(
            "late",
            3,
            "C3",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("turn"),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(
                Map.of(
                    "role",
                    "assistant",
                    "type",
                    "tool_use",
                    "id",
                    "tool-0",
                    "name",
                    "shell",
                    "input",
                    "late-input"),
                Map.of(
                    "role",
                    "user",
                    "type",
                    "tool_result",
                    "tool_call_id",
                    "tool-0",
                    "content",
                    "late-inline-result")),
            Map.of(),
            Map.of());
    units.add(
        unit(
            units.size(),
            List.of(late),
            List.of(),
            Map.of(
                "ref-0",
                entry("ref-0", "text", SourceUnitDirection.RESPONSE, "wrong-duplicate", Map.of())),
            List.of(new NormalizedSequenceChunk("responses", 0, List.of("ref-1")))));
    var content = new CountingContent(units, 3, 2, 7, 5);
    var reader =
        new com.feipi.session.browser.application.sessiondetail.SessionContentReader(content, 1);
    try (var bulk = reader.exportPayloads()) {
      var call = units.getFirst().calls().getFirst();
      assertThat(bulk.payload(call, false, PayloadVisibility.STANDARD))
          .isEqualTo(reader.payload(call, false, PayloadVisibility.STANDARD));
      assertThat(bulk.payload(call, false, PayloadVisibility.STANDARD).content())
          .contains("BODY-0-END", "BODY-1-END")
          .doesNotContain("wrong-duplicate", "late-input");
      for (String kind : List.of("input", "result")) {
        String id = "tool:" + kind + ":tool-0";
        assertThat(bulk.payload(id, PayloadVisibility.STANDARD))
            .isEqualTo(reader.payload(id, PayloadVisibility.STANDARD));
      }
      assertThat(
              bulk.payload("tool:result:tool-0", PayloadVisibility.STANDARD)
                  .orElseThrow()
                  .content())
          .isEqualTo("late-inline-result");
    }
  }

  static String export(NormalizedSessionContent content) throws Exception {
    var bytes = new ByteArrayOutputStream();
    try (var snapshot =
        ContentExportSnapshot.html(content, 1, PayloadVisibility.STANDARD, 50L * 1024 * 1024)) {
      snapshot.copyTo(bytes);
    }
    return bytes.toString(StandardCharsets.UTF_8);
  }

  static CountingContent fixture(int count) {
    var units = new ArrayList<NormalizedContentUnit>();
    for (int i = 0; i < count; i++) {
      var ranges =
          List.of(
              new SourceUnitRefRange(
                  Optional.of("responses"), 2 * i, 2 * i + 2, List.of(), Optional.of("assistant")));
      var call = call(i, CallScope.MAIN, ranges, Map.of(), NormalizedCallUsage.empty());
      units.add(unit(units.size(), List.of(call), List.of(), Map.of(), List.of()));
    }
    for (int i = 0; i < count; i++) {
      String ref = "ref-" + i;
      var body = entry(ref, "text", SourceUnitDirection.RESPONSE, "BODY-" + i + "-END", Map.of());
      var input =
          entry(
              "input-" + i,
              "tool_use",
              SourceUnitDirection.RESPONSE,
              "",
              Map.of(
                  "type",
                  "tool_use",
                  "id",
                  "tool-" + i,
                  "name",
                  "shell",
                  "input",
                  Map.of("command", "INPUT-" + i + "-END")));
      var result =
          entry(
              "result-" + i,
              "tool_result",
              SourceUnitDirection.REQUEST,
              "RESULT-" + i + "-END",
              Map.of("type", "tool_result", "tool_call_id", "tool-" + i));
      units.add(
          unit(
              units.size(),
              List.of(),
              List.of(),
              Map.of(ref, body, "input-" + i, input, "result-" + i, result),
              List.of(new NormalizedSequenceChunk("responses", 2L * i, List.of(ref, ref)))));
    }
    for (int i = 0; i < count; i++) {
      units.add(
          unit(
              units.size(),
              List.of(),
              List.of(
                  new NormalizedToolExecution(
                      "tool-" + i,
                      "shell",
                      CallScope.MAIN,
                      "call-" + i,
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      0,
                      List.of(),
                      Optional.empty())),
              Map.of(),
              List.of()));
    }
    return new CountingContent(units, count, count, 3L * count, 2L * count);
  }

  static NormalizedCall call(
      int i,
      CallScope scope,
      List<SourceUnitRefRange> ranges,
      Map<String, Object> precision,
      NormalizedCallUsage usage) {
    boolean sub = scope == CallScope.SUBAGENT;
    return new NormalizedCall(
        "call-" + i,
        i + 1,
        "C" + (i + 1),
        scope,
        sub ? Optional.of("call-0") : Optional.empty(),
        sub ? Optional.of("parent-tool") : Optional.empty(),
        Optional.of("turn"),
        "synthetic",
        Optional.empty(),
        usage,
        NormalizedCallRequest.empty(),
        new NormalizedCallResponse(List.of("tool-" + i)),
        ranges,
        List.of(),
        Map.of(),
        precision,
        sub ? Optional.of("agent-child") : Optional.empty(),
        sub ? Optional.of("delegate") : Optional.empty());
  }

  static NormalizedContentUnit unit(
      long index,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog,
      List<NormalizedSequenceChunk> sequences) {
    return new NormalizedContentUnit(index, List.of(), calls, tools, List.of(), catalog, sequences);
  }

  private static SourceUnitCatalogEntry entry(
      String key, String type, SourceUnitDirection direction, String text, Object payload) {
    return new SourceUnitCatalogEntry(
        key,
        "synthetic.jsonl",
        "synthetic:" + key,
        type,
        "synthetic",
        direction,
        0,
        0,
        new ByteRange(0, 1),
        "synthetic-hash",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.of(text),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  static final class CountingContent implements NormalizedSessionContent {
    final List<NormalizedContentUnit> units;
    private final NormalizedContentHeader header;
    int opens;
    int reads;

    CountingContent(
        List<NormalizedContentUnit> units, long calls, long tools, long catalog, long sequence) {
      this.units = List.copyOf(units);
      header =
          new NormalizedContentHeader(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CODEX,
              new NormalizedSessionMetadata(Map.of()),
              Map.of(
                  "calls",
                  calls,
                  "toolExecutions",
                  tools,
                  "diagnostics",
                  0L,
                  "sourceFiles",
                  0L,
                  "sourceUnitCatalog",
                  catalog,
                  "sourceUnitSequenceEntries",
                  sequence));
    }

    public NormalizedContentHeader header() {
      return header;
    }

    public ContentCursor openCursor() {
      opens++;
      var iterator = units.iterator();
      return new ContentCursor() {
        public boolean hasNext() {
          return iterator.hasNext();
        }

        public NormalizedContentUnit next() {
          reads++;
          return iterator.next();
        }

        public void close() {}
      };
    }
  }
}
