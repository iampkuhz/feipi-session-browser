package com.feipi.session.browser.application.sessiondetail;

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
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** Round 按钮的流式完整正文契约，不能通过物化旧制品实现。 */
class StreamingRoundPayloadTest {
  @Test
  void roundReadingDoesNotBorrowRoleFromAnotherCallReferencingTheSameText() throws Exception {
    var calls =
        IntStream.rangeClosed(1, 2)
            .mapToObj(
                i ->
                    new NormalizedCall(
                        "c" + i,
                        i,
                        "C" + i,
                        CallScope.MAIN,
                        Optional.empty(),
                        Optional.empty(),
                        Optional.of("shared-turn"),
                        "synthetic-model",
                        Optional.empty(),
                        NormalizedCallUsage.empty(),
                        NormalizedCallRequest.empty(),
                        NormalizedCallResponse.empty(),
                        List.of(
                            new SourceUnitRefRange(
                                Optional.empty(),
                                0,
                                1,
                                List.of("shared"),
                                i == 1 ? Optional.of("user") : Optional.empty())),
                        List.of(),
                        Map.of(),
                        Map.of()))
            .toList();
    var entries =
        Map.of(
            "shared",
            catalog("shared", "message", SourceUnitDirection.REQUEST, Map.of("text", "SHARED")));
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            calls,
            List.of(),
            List.of(),
            entries,
            Map.of());
    var content =
        stream(
            artifact,
            List.of(
                new NormalizedContentUnit(
                    0, List.of(), calls, List.of(), List.of(), entries, List.of())));
    var reader = new SessionContentReader(content, 1);
    var first = reader.payload("main:req:c1", PayloadVisibility.FULL).orElseThrow();
    var second = reader.payload("main:req:c2", PayloadVisibility.FULL).orElseThrow();
    var round = reader.payload("round:req:1", PayloadVisibility.FULL).orElseThrow();
    assertThat(first.reading())
        .extracting(PayloadLookup.ReadingBlock::text)
        .containsExactly("SHARED");
    assertThat(second.reading()).isEmpty();
    assertThat(round.content()).isEqualTo("C1 · c1\nSHARED\n\nC2 · c2\nSHARED");
    assertThat(round.reading()).containsExactly(new PayloadLookup.ReadingBlock("C1", "SHARED"));
  }

  @Test
  void roundBodiesMatchLegacyAndPreferMainCallsAcrossMoreThan500Members() throws Exception {
    var calls = new java.util.ArrayList<NormalizedCall>();
    for (int i = 1; i <= 503; i++) calls.add(call(i, CallScope.MAIN, Optional.empty()));
    calls.add(call(504, CallScope.SUBAGENT, Optional.of("c1")));
    assertEquivalent(calls);
  }

  @Test
  void orphanChildRoundKeepsItsRequestAndResponse() throws Exception {
    assertEquivalent(List.of(call(1, CallScope.SUBAGENT, Optional.empty())));
  }

  @Test
  void missingAndInvalidRoundsReturnEmpty() throws Exception {
    var reader =
        new SessionContentReader(
            stream(artifact(List.of(call(1, CallScope.MAIN, Optional.empty())))), 1);
    for (String id :
        List.of(
            "round:req:0",
            "round:resp:2",
            "round:req:-1",
            "round:req:x",
            "round:req:2147483648",
            "round:other:1",
            "round:req:1:extra")) {
      assertThat(reader.payload(id, PayloadVisibility.FULL)).as(id).isEmpty();
    }
  }

  @Test
  void crossUnitSequenceCatalogAndToolBodiesMatchLegacy() throws Exception {
    var original = call(1, CallScope.MAIN, Optional.empty());
    var call =
        new NormalizedCall(
            original.callId(),
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("shared-turn"),
            "synthetic-model",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            new NormalizedCallResponse(List.of("tool1")),
            List.of(
                new SourceUnitRefRange(Optional.of("messages"), 0, 2, List.of(), Optional.empty())),
            original.sourceUnits(),
            Map.of(),
            Map.of());
    var catalog =
        Map.of(
            "req",
                catalog(
                    "req",
                    "user_message",
                    SourceUnitDirection.REQUEST,
                    Map.of(
                        "role",
                        "user",
                        "text",
                        "catalog request {\"api_key\":\"synthetic-secret\"}")),
            "resp",
                catalog(
                    "resp",
                    "assistant_message",
                    SourceUnitDirection.RESPONSE,
                    Map.of("role", "assistant", "text", "catalog response")),
            "tool",
                catalog(
                    "tool",
                    "tool_use",
                    SourceUnitDirection.RESPONSE,
                    Map.of(
                        "type",
                        "tool_use",
                        "id",
                        "tool1",
                        "name",
                        "Bash",
                        "input",
                        "echo synthetic")));
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(call),
            List.of(),
            List.of(),
            catalog,
            Map.of("messages", List.of("req", "resp")));
    var units =
        List.of(
            new NormalizedContentUnit(
                0, List.of(), List.of(call), List.of(), List.of(), Map.of(), List.of()),
            new NormalizedContentUnit(
                1,
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                Map.of(),
                List.of(new NormalizedSequenceChunk("messages", 0, List.of("req", "resp")))),
            new NormalizedContentUnit(
                2, List.of(), List.of(), List.of(), List.of(), catalog, List.of()));
    var reader = new SessionContentReader(stream(artifact, units), 1);
    for (var visibility : PayloadVisibility.values()) {
      var legacy = PayloadLookup.fromArtifact(artifact, visibility);
      for (String side : List.of("req", "resp")) {
        String id = "round:" + side + ":1";
        var actual = reader.payload(id, visibility).orElseThrow();
        assertThat(actual).isEqualTo(legacy.lookup(id).orElseThrow());
        assertThat(actual.content())
            .contains("catalog " + (side.equals("req") ? "request" : "response"))
            .doesNotContain("req-1", "resp-1");
      }
      assertThat(reader.payload("round:resp:1", visibility).orElseThrow().content())
          .contains("工具指令", "Bash [tool1]", "echo synthetic");
    }
  }

  @Test
  void catalogRoundReadsAll503CallsWithConstantCursorReplays() throws Exception {
    var calls = new java.util.ArrayList<NormalizedCall>();
    var entries = new java.util.LinkedHashMap<String, SourceUnitCatalogEntry>();
    var units = new java.util.ArrayList<NormalizedContentUnit>();
    for (int i = 1; i <= 503; i++) {
      var base = call(i, CallScope.MAIN, Optional.empty());
      var call =
          new NormalizedCall(
              base.callId(),
              i,
              base.callKey(),
              base.scope(),
              Optional.empty(),
              Optional.empty(),
              base.turnId(),
              base.model(),
              Optional.empty(),
              base.usage(),
              base.request(),
              base.response(),
              List.of(
                  new SourceUnitRefRange(
                      Optional.of("messages"), i - 1, i, List.of(), Optional.of("user"))),
              List.of(),
              Map.of(),
              Map.of());
      calls.add(call);
      entries.put(
          "r" + i,
          catalog(
              "r" + i,
              "user_message",
              SourceUnitDirection.REQUEST,
              Map.of("role", "user", "text", "cross-unit-body-" + i)));
      units.add(
          new NormalizedContentUnit(
              i - 1, List.of(), List.of(call), List.of(), List.of(), Map.of(), List.of()));
    }
    var keys = IntStream.rangeClosed(1, 503).mapToObj(i -> "r" + i).toList();
    units.add(
        new NormalizedContentUnit(
            503,
            List.of(),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            List.of(new NormalizedSequenceChunk("messages", 0, keys.subList(0, 250)))));
    units.add(
        new NormalizedContentUnit(
            504,
            List.of(),
            List.of(),
            List.of(),
            List.of(),
            entries,
            List.of(new NormalizedSequenceChunk("messages", 250, keys.subList(250, 503)))));
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            calls,
            List.of(),
            List.of(),
            entries,
            Map.of("messages", keys));
    var source = stream(artifact, units);
    var opens = new java.util.concurrent.atomic.AtomicInteger();
    var counted =
        new NormalizedSessionContent() {
          public NormalizedContentHeader header() {
            return source.header();
          }

          public NormalizedSessionArtifact toArtifact() {
            throw new AssertionError("must not flatten");
          }

          public ContentCursor openCursor() throws java.io.IOException {
            opens.incrementAndGet();
            return source.openCursor();
          }
        };
    var reader = new SessionContentReader(counted, 1);
    opens.set(0);
    var actual = reader.payload("round:req:1", PayloadVisibility.FULL).orElseThrow();
    assertThat(actual.content())
        .startsWith("C1 · c1\ncross-unit-body-1\n\nC2 · c2\n")
        .endsWith("C503 · c503\ncross-unit-body-503");
    for (int i = 1; i <= 503; i++) {
      assertThat(actual.content()).contains("C" + i + " · c" + i + "\ncross-unit-body-" + i);
    }
    assertThat(actual)
        .isEqualTo(
            PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL)
                .lookup("round:req:1")
                .orElseThrow());
    assertThat(opens.get()).as("no per-call source replay").isLessThanOrEqualTo(4);
  }

  @Test
  void roundToolInstructionsKeepCatalogOrderRatherThanDeclarationOrder() throws Exception {
    var entries =
        Map.of(
            "tool-a",
                catalog(
                    "tool-a",
                    "tool_use",
                    SourceUnitDirection.RESPONSE,
                    Map.of(
                        "type",
                        "tool_use",
                        "id",
                        "tool-a",
                        "name",
                        "ToolA",
                        "input",
                        "alpha-body")),
            "tool-b",
                catalog(
                    "tool-b",
                    "tool_use",
                    SourceUnitDirection.RESPONSE,
                    Map.of(
                        "type",
                        "tool_use",
                        "id",
                        "tool-b",
                        "name",
                        "ToolB",
                        "input",
                        "beta-body")));
    var catalogArtifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(),
            List.of(),
            List.of(),
            entries,
            Map.of());
    var order =
        catalogArtifact.sourceUnitCatalog().values().stream()
            .map(entry -> (String) ((Map<?, ?>) entry.payload()).get("id"))
            .toList();
    var base = call(1, CallScope.MAIN, Optional.empty());
    var call =
        new NormalizedCall(
            base.callId(),
            1,
            base.callKey(),
            base.scope(),
            Optional.empty(),
            Optional.empty(),
            base.turnId(),
            base.model(),
            Optional.empty(),
            base.usage(),
            base.request(),
            new NormalizedCallResponse(List.of(order.get(1), order.get(0))),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(call),
            List.of(),
            List.of(),
            catalogArtifact.sourceUnitCatalog(),
            Map.of());
    var units =
        List.of(
            new NormalizedContentUnit(
                0,
                List.of(),
                List.of(call),
                List.of(),
                List.of(),
                artifact.sourceUnitCatalog(),
                List.of()));
    var expected =
        PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL)
            .lookup("round:resp:1")
            .orElseThrow();
    assertThat(expected.content())
        .contains("ToolA [tool-a]\nalpha-body", "ToolB [tool-b]\nbeta-body");
    assertThat(expected.content().indexOf("[" + order.get(0) + "]"))
        .isLessThan(expected.content().indexOf("[" + order.get(1) + "]"));
    var reader = new SessionContentReader(stream(artifact, units), 1);
    assertThat(reader.payload("round:resp:1", PayloadVisibility.FULL)).contains(expected);
  }

  @Test
  void observedUserMessageWithoutCallsDoesNotInventRoundPayload() throws Exception {
    var artifact = artifact(List.of());
    var reader = new SessionContentReader(stream(artifact), 1);
    assertThat(reader.roundIndex().roundCount()).isEqualTo(1);
    for (String id : List.of("round:req:1", "round:resp:1")) {
      assertThat(PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL).lookup(id)).isEmpty();
      assertThat(reader.payload(id, PayloadVisibility.FULL)).isEmpty();
    }
  }

  private static SourceUnitCatalogEntry catalog(
      String key, String type, SourceUnitDirection direction, Map<String, Object> payload) {
    return new SourceUnitCatalogEntry(
        key,
        "synthetic.jsonl",
        "synthetic#" + key,
        type,
        "",
        direction,
        0,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.empty(),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static void assertEquivalent(List<NormalizedCall> calls) throws Exception {
    var artifact = artifact(calls);
    var reader = new SessionContentReader(stream(artifact), 1);
    for (var visibility : PayloadVisibility.values()) {
      var legacy = PayloadLookup.fromArtifact(artifact, visibility);
      for (String side : List.of("req", "resp")) {
        String id = "round:" + side + ":1";
        var actual = reader.payload(id, visibility).orElseThrow();
        assertThat(actual).isEqualTo(legacy.lookup(id).orElseThrow());
        assertThat(actual.content()).contains("C1 · c1\n", side + "-1");
        if (calls.size() > 500) {
          assertThat(actual.content()).contains(side + "-503").doesNotContain(side + "-504");
        }
        assertThat(actual.truncated()).isFalse();
        if (side.equals("req")) {
          if (visibility == PayloadVisibility.FULL)
            assertThat(actual.content()).contains("synthetic-secret");
          else
            assertThat(actual.content()).contains("[REDACTED]").doesNotContain("synthetic-secret");
        }
        if (calls.size() > 500) {
          assertThat(actual.content()).contains("\n\nC2 · c2\n" + side + "-2");
          assertThat(actual.content().indexOf(side + "-1"))
              .isLessThan(actual.content().indexOf(side + "-503"));
        }
      }
    }
  }

  private static NormalizedSessionArtifact artifact(List<NormalizedCall> calls) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CODEX,
        List.of(),
        Map.of(),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int i, CallScope scope, Optional<String> parent) {
    return new NormalizedCall(
        "c" + i,
        i,
        "C" + i,
        scope,
        parent,
        Optional.empty(),
        Optional.of("shared-turn"),
        "synthetic-model",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(
            Map.of("role", "user", "text", "req-" + i + " {\"api_key\":\"synthetic-secret\"}"),
            Map.of("role", "assistant", "text", "resp-" + i)),
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionContent stream(NormalizedSessionArtifact artifact) {
    var units =
        IntStream.range(0, artifact.calls().size())
            .mapToObj(
                i ->
                    new NormalizedContentUnit(
                        i,
                        List.of(),
                        List.of(artifact.calls().get(i)),
                        List.of(),
                        List.of(),
                        Map.of(),
                        List.of()))
            .toList();
    return stream(artifact, units);
  }

  private static NormalizedSessionContent stream(
      NormalizedSessionArtifact artifact, List<NormalizedContentUnit> units) {
    var header = NormalizedSessionContent.fromArtifact(artifact).header();
    return new NormalizedSessionContent() {
      public NormalizedContentHeader header() {
        return header;
      }

      public NormalizedSessionArtifact toArtifact() {
        throw new AssertionError("must not flatten");
      }

      public ContentCursor openCursor() {
        var iterator = units.iterator();
        return new ContentCursor() {
          public boolean hasNext() {
            return iterator.hasNext();
          }

          public NormalizedContentUnit next() {
            return iterator.next();
          }

          public void close() {}
        };
      }
    };
  }
}
