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
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 合成内容从声明到调用/round payload 的保真契约。 */
class ToolPayloadSemanticsTest {
  @Test
  void catalogUserMessagesUseCallRefsAndExcludeToolResults() {
    var range =
        new SourceUnitRefRange(
            Optional.of("request-sequence"), 0, 2, List.of(), Optional.of("user"));
    var call =
        new NormalizedCall(
            "c1",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            "fixture-model",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(range),
            List.of(),
            Map.of(),
            Map.of());
    var message =
        catalog(
            "user",
            "user_message",
            SourceUnitDirection.REQUEST,
            Map.of("role", "user", "text", "catalog user input"));
    var result =
        catalog(
            "result",
            "tool_result",
            SourceUnitDirection.REQUEST,
            Map.of("role", "user", "type", "tool_result", "content", "not user input"));
    var other =
        catalog(
            "other",
            "user_message",
            SourceUnitDirection.REQUEST,
            Map.of("role", "user", "text", "unrelated user input"));
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.QODER,
            List.of(),
            Map.of(),
            List.of(call),
            List.of(),
            List.of(),
            Map.of("user", message, "result", result, "other", other),
            Map.of("request-sequence", List.of("user", "result")));
    assertThat(PayloadCallContentExtractor.extractUserMessageTexts(call, artifact))
        .containsExactly("catalog user input");
  }

  @Test
  void catalogToolInputsAndRequestSideResultsRemainDistinct() {
    String command = "{\"command\":\"echo catalog\"}";
    var call = call("c1", 1, List.of("tool1"), List.of());
    var input =
        catalog("input", "tool_use", SourceUnitDirection.RESPONSE, input("tool1", "Bash", command));
    var result =
        catalog(
            "result",
            "tool_result",
            SourceUnitDirection.REQUEST,
            Map.of("type", "tool_result", "tool_call_id", "tool1", "content", "catalog output"));
    var execution =
        new NormalizedToolExecution(
            "tool1",
            "Bash",
            CallScope.MAIN,
            "c1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            0,
            List.of(),
            Optional.empty());
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.QODER,
            List.of(),
            Map.of(),
            List.of(call),
            List.of(execution),
            List.of(),
            Map.of("input", input, "result", result),
            Map.of());
    var lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
    assertThat(lookup.lookup("tool:input:tool1").orElseThrow().content()).isEqualTo(command);
    assertThat(lookup.lookup("tool:result:tool1").orElseThrow().content())
        .isEqualTo("catalog output");
    assertThat(lookup.lookup("main:resp:c1").orElseThrow().content())
        .contains(command)
        .doesNotContain("catalog output");
  }

  @Test
  void contentPayloadsResolveCallsSequencesCatalogAndToolsAcrossUnits() throws Exception {
    var call =
        new NormalizedCall(
            "cross",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("turn"),
            "synthetic-model",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            new NormalizedCallResponse(List.of("tool-cross")),
            List.of(
                new SourceUnitRefRange(
                    Optional.of("messages"), 0, 1, List.of(), Optional.of("user"))),
            List.of(),
            Map.of(),
            Map.of());
    String secret = "{\"api_key\":\"synthetic-secret\",\"command\":\"echo last\"}";
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.QODER,
            List.of(),
            Map.of(),
            List.of(call),
            List.of(),
            List.of(),
            Map.of(
                "user",
                catalog(
                    "user",
                    "user_message",
                    SourceUnitDirection.REQUEST,
                    Map.of("role", "user", "text", "cross-unit request")),
                "input",
                catalog(
                    "input",
                    "tool_use",
                    SourceUnitDirection.RESPONSE,
                    input("tool-cross", "Bash", secret)),
                "result",
                catalog(
                    "result",
                    "tool_result",
                    SourceUnitDirection.REQUEST,
                    Map.of(
                        "type",
                        "tool_result",
                        "tool_call_id",
                        "tool-cross",
                        "content",
                        "cross-unit result"))),
            Map.of("messages", List.of("user")));
    var header =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(artifact)
            .header();
    var units =
        List.of(
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                0, List.of(), List.of(call), List.of(), List.of(), Map.of(), List.of()),
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                1,
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                Map.of(),
                List.of(
                    new com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk(
                        "messages", 0, List.of("user")))),
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                2,
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                artifact.sourceUnitCatalog(),
                List.of()));
    var content =
        new com.feipi.session.browser.domain.normalized.NormalizedSessionContent() {
          public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
            return header;
          }

          public ContentCursor openCursor() {
            var iterator = units.iterator();
            return new ContentCursor() {
              public boolean hasNext() {
                return iterator.hasNext();
              }

              public com.feipi.session.browser.domain.normalized.NormalizedContentUnit next() {
                return iterator.next();
              }

              public void close() {}
            };
          }
        };
    var reader = new SessionContentReader(content, 1);
    assertThat(reader.payload("main:req:cross", PayloadVisibility.FULL).orElseThrow().content())
        .isEqualTo("cross-unit request");
    assertThat(
            reader.payload("main:resp:cross", PayloadVisibility.STANDARD).orElseThrow().content())
        .contains("echo last", "[REDACTED]")
        .doesNotContain("synthetic-secret", "cross-unit result");
    assertThat(
            reader.payload("tool:input:tool-cross", PayloadVisibility.FULL).orElseThrow().content())
        .isEqualTo(secret);
    assertThat(
            reader
                .payload("tool:result:tool-cross", PayloadVisibility.FULL)
                .orElseThrow()
                .content())
        .isEqualTo("cross-unit result");
    assertThat(reader.payload("main:resp:missing", PayloadVisibility.FULL)).isEmpty();
  }

  @Test
  void alreadyVisitedCallPayloadDoesNotSearchForCallIdentityAgain() throws Exception {
    var call =
        call(
            "visited",
            1,
            List.of(),
            List.of(Map.of("role", "assistant", "text", "inline export tail")));
    var empty =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
            artifact(List.of()));
    var indexed = new java.util.concurrent.atomic.AtomicBoolean(false);
    var guarded =
        new com.feipi.session.browser.domain.normalized.NormalizedSessionContent() {
          public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
            return empty.header();
          }

          public ContentCursor openCursor() throws java.io.IOException {
            if (indexed.get()) throw new AssertionError("inline payload must not reopen content");
            return empty.openCursor();
          }
        };
    var reader = new SessionContentReader(guarded, 0);
    indexed.set(true);
    assertThat(reader.payload(call, false, PayloadVisibility.FULL).content())
        .isEqualTo("inline export tail");
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

  @Test
  void responseIncludesTextAndEveryInstructionButAssistantPreviewOnlyContainsText() {
    String command = "{\"command\":\"printf '<synthetic>'\\nprintf 'end'\"}";
    var call =
        call(
            "c1",
            1,
            List.of("read1", "bash1"),
            List.of(
                Map.of("type", "text", "role", "assistant", "text", "先读取再检查"),
                input("read1", "Read", "{\"file_path\":\"/synthetic/a.md\"}"),
                input("bash1", "Bash", command)));
    var artifact = artifact(List.of(call));
    String response = PayloadCallContentExtractor.extractResponseContent(call, artifact);
    assertThat(response).contains("先读取再检查", "Read [read1]", "Bash [bash1]", command);
    assertThat(PayloadCallContentExtractor.extractAssistantText(call, artifact))
        .isEqualTo("先读取再检查");
    assertThat(
            PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL)
                .lookup("tool:input:bash1")
                .orElseThrow()
                .content())
        .isEqualTo(command);
  }

  @Test
  void roundPayloadIncludesAllFragmentsAndRequestResultsStayOnRequestSide() {
    var text =
        call(
            "c1",
            1,
            List.of(),
            List.of(
                Map.of("type", "text", "role", "assistant", "text", "分析说明"),
                Map.of(
                    "type",
                    "tool_result",
                    "role",
                    "user",
                    "tool_call_id",
                    "previous",
                    "content",
                    "先前结果")));
    var tool =
        call(
            "c2",
            2,
            List.of("read1"),
            List.of(input("read1", "Read", "{\"file_path\":\"/synthetic/last.md\"}")));
    var lookup = PayloadLookup.fromArtifact(artifact(List.of(text, tool)), PayloadVisibility.FULL);
    assertThat(lookup.lookup("round:resp:1").orElseThrow().content())
        .contains("分析说明", "Read [read1]", "/synthetic/last.md")
        .doesNotContain("先前结果");
    assertThat(lookup.lookup("round:req:1").orElseThrow().content())
        .contains("Tool result [previous]", "先前结果")
        .doesNotContain("last.md");
  }

  @Test
  void missingParametersAreExplicitAndStandardVisibilityMasksJsonSecrets() {
    var missing = call("c1", 1, List.of("missing"), List.of());
    var artifact = artifact(List.of(missing));
    assertThat(PayloadCallContentExtractor.extractResponseContent(missing, artifact))
        .contains("missing", "输入未记录", "重新扫描");
    assertThat(
            PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD)
                .lookup("tool:input:missing")
                .orElseThrow()
                .content())
        .isEmpty();

    String secretInput = "{\"api_key\":\"synthetic-credential\",\"file_path\":\"/synthetic/a\"}";
    var tool = call("c2", 2, List.of("read1"), List.of(input("read1", "Read", secretInput)));
    var lookup = PayloadLookup.fromArtifact(artifact(List.of(tool)), PayloadVisibility.STANDARD);
    assertThat(lookup.lookup("tool:input:read1").orElseThrow().content())
        .contains("[REDACTED]", "/synthetic/a")
        .doesNotContain("synthetic-credential");
    assertThat(lookup.lookup("main:resp:c2").orElseThrow().truncated()).isFalse();
  }

  private static Map<String, Object> input(String id, String name, String content) {
    return Map.of(
        "type", "tool_use", "role", "assistant", "id", id, "name", name, "input", content);
  }

  private static NormalizedCall call(
      String id, int index, List<String> toolIds, List<Map<String, Object>> units) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of("synthetic-message"),
        "synthetic-model",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        NormalizedCallRequest.empty(),
        new NormalizedCallResponse(toolIds),
        List.of(),
        units,
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionArtifact artifact(List<NormalizedCall> calls) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.QODER,
        List.of(),
        Map.of(),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
