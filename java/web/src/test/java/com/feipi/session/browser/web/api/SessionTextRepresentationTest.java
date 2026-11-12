package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 同一组事实更换存储表示，摘要、可见正文与原始 payload 保持一致，不重复计消息。 */
class SessionTextRepresentationTest {
  @ParameterizedTest
  @ValueSource(strings = {"inline", "catalog", "sequence", "both"})
  void textRepresentationsHaveSameSummaryReadingAndPayload(String representation) throws Exception {
    var artifact = artifact(representation);
    var call = artifact.calls().getFirst();
    var content = NormalizedSessionContent.fromArtifact(artifact);
    var reader = new SessionContentReader(content, 1);
    var lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
    assertThat(PayloadCallContentExtractor.extractUserMessageTexts(call, artifact))
        .containsExactly("synthetic question");
    for (String side : List.of("req", "resp")) {
      String id = "main:" + side + ":c1";
      String expected = side.equals("req") ? "synthetic question" : "synthetic answer";
      var streamed = reader.payload(id, PayloadVisibility.FULL).orElseThrow();
      var legacy = lookup.lookup(id).orElseThrow();
      assertThat(streamed.content()).isEqualTo(expected).isEqualTo(legacy.content());
      assertThat(streamed.reading())
          .extracting(PayloadLookup.ReadingBlock::text)
          .containsExactly(expected);
      assertThat(streamed.reading()).isEqualTo(legacy.reading());
      assertThat(
              reader
                  .payload("round:" + side + ":1", PayloadVisibility.FULL)
                  .orElseThrow()
                  .content())
          .contains(expected);
    }
    var rows =
        SessionContentProjection.rounds(
            SessionDetailParityAnalyzerTest.healthDetail(false, 0), content);
    assertThat(rows).hasSize(1);
    assertThat(rows.getFirst().callCount()).isEqualTo(1);
    assertThat(rows.getFirst().toolCallCount()).isZero();
    assertThat(rows.getFirst().parity()).containsEntry("summary", "synthetic question");
    assertThat(rows.getFirst().tokens().provenance().freshInput()).isEqualTo("unknown");
  }

  private static NormalizedSessionArtifact artifact(String representation) {
    boolean inline = List.of("inline", "both").contains(representation);
    boolean sequence = "sequence".equals(representation);
    var ranges =
        "inline".equals(representation)
            ? List.<SourceUnitRefRange>of()
            : List.of(range("user", 0, sequence), range("assistant", 1, sequence));
    var call =
        new NormalizedCall(
            "c1",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("synthetic-turn"),
            "synthetic-model",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            ranges,
            inline
                ? List.of(
                    Map.of("role", "user", "type", "text", "text", "synthetic question"),
                    Map.of("role", "assistant", "type", "text", "text", "synthetic answer"))
                : List.of(),
            Map.of(),
            Map.of());
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of(),
        List.of(call),
        List.of(),
        List.of(),
        inline && !"both".equals(representation)
            ? Map.of()
            : Map.of(
                "user", entry("user", "synthetic question", true),
                "assistant", entry("assistant", "synthetic answer", false)),
        sequence ? Map.of("messages", List.of("user", "assistant")) : Map.of());
  }

  private static SourceUnitRefRange range(String role, int index, boolean sequence) {
    return new SourceUnitRefRange(
        sequence ? Optional.of("messages") : Optional.empty(),
        index,
        index + 1,
        sequence ? List.of() : List.of(role),
        Optional.of(role));
  }

  private static SourceUnitCatalogEntry entry(String role, String text, boolean request) {
    return new SourceUnitCatalogEntry(
        role,
        "/synthetic/session.jsonl",
        "fixture:" + role,
        role,
        "visible",
        request ? SourceUnitDirection.REQUEST : SourceUnitDirection.RESPONSE,
        request ? 0 : 1,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.of(text),
        Map.of("role", role),
        Optional.empty(),
        Optional.empty(),
        List.of());
  }
}
