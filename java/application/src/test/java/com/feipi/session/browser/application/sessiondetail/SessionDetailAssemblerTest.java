package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link SessionDetailAssembler} 测试。
 *
 * <p>覆盖调用轮次分组、payload 来源生成和缓存键构建。
 */
@DisplayName("SessionDetailAssembler 测试")
class SessionDetailAssemblerTest {

  private static final SessionRow TEST_ROW =
      new SessionRow(
          "cc:s1",
          "claude_code",
          "s1",
          "测试会话",
          "pk1",
          "项目一",
          "/work",
          "2024-01-01T00:00:00Z",
          "2024-01-01T01:00:00Z",
          3600,
          3000,
          600,
          "claude-3-opus",
          "main",
          "cli",
          5,
          10,
          20,
          50000,
          25000,
          15000,
          10000,
          100000,
          0,
          2,
          1704067200,
          1704067200,
          "/f1");

  @Nested
  @DisplayName("buildRounds 轮次分组")
  class BuildRounds {

    @Test
    @DisplayName("空调用列表返回空轮次")
    void emptyCalls() {
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of());
      assertThat(rounds).isEmpty();
    }

    @Test
    @DisplayName("单个主调用创建一个轮次")
    void singleMainCall() {
      NormalizedCall call = makeCall("c1", 1, CallScope.MAIN, Optional.empty());
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(call));
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).roundIndex()).isEqualTo(1);
      assertThat(rounds.get(0).calls()).containsExactly("c1");
    }

    @Test
    @DisplayName("多个主调用创建多个轮次")
    void multipleMainCalls() {
      NormalizedCall call1 = makeCall("c1", 1, CallScope.MAIN, Optional.empty());
      NormalizedCall call2 = makeCall("c2", 2, CallScope.MAIN, Optional.empty());
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(call1, call2));
      assertThat(rounds).hasSize(2);
      assertThat(rounds.get(0).calls()).containsExactly("c1");
      assertThat(rounds.get(1).calls()).containsExactly("c2");
    }

    @Test
    @DisplayName("同一 provider turn 的多条主调用合并为一个逻辑轮次")
    void sameTurnMainCallsMerged() {
      NormalizedCall call1 = makeCallWithTurn("c1", 1, "msg-1", List.of(), List.of("tool-1"));
      NormalizedCall call2 = makeCallWithTurn("c2", 2, "msg-1", List.of("tool-1"), List.of());
      NormalizedCall call3 = makeCallWithTurn("c3", 3, "msg-2", List.of(), List.of());
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(call1, call2, call3));
      assertThat(rounds).hasSize(2);
      assertThat(rounds.get(0).calls()).containsExactly("c1", "c2");
      assertThat(rounds.get(0).toolCallIds()).containsExactly("tool-1");
      assertThat(rounds.get(1).calls()).containsExactly("c3");
    }

    @Test
    @DisplayName("子 agent 调用合并到父调用轮次")
    void subagentCallMergedToParent() {
      NormalizedCall mainCall = makeCall("c1", 1, CallScope.MAIN, Optional.empty());
      NormalizedCall subCall = makeCall("c2", 2, CallScope.SUBAGENT, Optional.of("c1"));
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(mainCall, subCall));
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).calls()).containsExactly("c1", "c2");
    }

    @Test
    @DisplayName("轮次聚合 main 和 subagent token usage")
    void roundAggregatesUsage() {
      NormalizedCall mainCall =
          makeCall(
              "c1",
              1,
              CallScope.MAIN,
              Optional.empty(),
              new NormalizedCallUsage(10, 20, 5, 15, 50));
      NormalizedCall subCall =
          makeCall(
              "c2",
              2,
              CallScope.SUBAGENT,
              Optional.of("c1"),
              new NormalizedCallUsage(3, 4, 2, 1, 10));
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(mainCall, subCall));
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).freshInputTokens()).isEqualTo(13);
      assertThat(rounds.get(0).cacheReadTokens()).isEqualTo(24);
      assertThat(rounds.get(0).cacheWriteTokens()).isEqualTo(7);
      assertThat(rounds.get(0).outputTokens()).isEqualTo(16);
      assertThat(rounds.get(0).totalTokens()).isEqualTo(60);
    }

    @Test
    @DisplayName("轮次聚合失败工具调用 ID")
    void roundAggregatesFailedToolIds() {
      NormalizedCall call1 = makeCall("c1", 1, CallScope.MAIN, Optional.empty());
      NormalizedCall call2 = makeCall("c2", 2, CallScope.MAIN, Optional.empty());
      List<CallRound> rounds =
          SessionDetailAssembler.buildRounds(
              List.of(call1, call2),
              List.of(
                  makeToolExecution("tool-ok", "c1", Optional.empty()),
                  makeToolExecution("tool-failed", "c2", Optional.of("error: failed"))));

      assertThat(rounds).hasSize(2);
      assertThat(rounds.get(0).failedToolCallIds()).isEmpty();
      assertThat(rounds.get(1).failedToolCallIds()).containsExactly("tool-failed");
      assertThat(rounds.get(1).failedToolCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("无父调用的子 agent 创建独立轮次")
    void orphanSubagentCall() {
      NormalizedCall subCall = makeCall("c1", 1, CallScope.SUBAGENT, Optional.of("missing"));
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(subCall));
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).calls()).containsExactly("c1");
      assertThat(rounds.get(0).parentCallId()).isEqualTo("missing");
    }
  }

  @Nested
  @DisplayName("buildPayloadSources payload 来源")
  class BuildPayloadSources {

    @Test
    @DisplayName("每次调用生成请求和响应 payload")
    void callGeneratesPayload() {
      NormalizedCall call =
          new NormalizedCall(
              "c1",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      List<PayloadSource> sources =
          SessionDetailAssembler.buildPayloadSources(List.of(call), PayloadVisibility.STANDARD);
      assertThat(sources).hasSize(2);
      assertThat(sources.get(0).kind()).isEqualTo(PayloadSourceKind.LLM_REQUEST);
      assertThat(sources.get(0).truncated()).isFalse();
      assertThat(sources.get(1).kind()).isEqualTo(PayloadSourceKind.LLM_RESPONSE);
    }

    @Test
    @DisplayName("完整可见性不截断")
    void fullVisibilityNotTruncated() {
      NormalizedCall call =
          new NormalizedCall(
              "c1",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      List<PayloadSource> sources =
          SessionDetailAssembler.buildPayloadSources(List.of(call), PayloadVisibility.FULL);
      assertThat(sources).allMatch(s -> !s.truncated());
    }

    @Test
    @DisplayName("子 agent 调用使用 SUBAGENT 类型")
    void subagentCallPayloadKind() {
      NormalizedCall call =
          new NormalizedCall(
              "c1",
              1,
              "C1",
              CallScope.SUBAGENT,
              Optional.of("parent"),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      List<PayloadSource> sources =
          SessionDetailAssembler.buildPayloadSources(List.of(call), PayloadVisibility.STANDARD);
      assertThat(sources).hasSize(2);
      assertThat(sources.get(0).kind()).isEqualTo(PayloadSourceKind.SUBAGENT_REQUEST);
      assertThat(sources.get(1).kind()).isEqualTo(PayloadSourceKind.SUBAGENT_RESPONSE);
    }
  }

  @Nested
  @DisplayName("buildCacheKey 缓存键")
  class BuildCacheKey {

    @Test
    @DisplayName("包含制品路径和版本")
    void withPath() {
      String key = SessionDetailAssembler.buildCacheKey("/artifacts/test.json", 1);
      assertThat(key).isEqualTo("artifact:/artifacts/test.json:v1");
    }

    @Test
    @DisplayName("空路径使用 novalue 前缀")
    void emptyPath() {
      String key = SessionDetailAssembler.buildCacheKey("", 1);
      assertThat(key).isEqualTo("novalue:v1");
    }

    @Test
    @DisplayName("null 路径使用 novalue 前缀")
    void nullPath() {
      String key = SessionDetailAssembler.buildCacheKey(null, 2);
      assertThat(key).isEqualTo("novalue:v2");
    }
  }

  @Nested
  @DisplayName("assemble 完整装配")
  class Assemble {

    @Test
    void persistedRoundCountMatchesDetailForMultipleCallsInOneTurn() {
      var artifact =
          new NormalizedSessionArtifact(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CLAUDE_CODE,
              List.of(),
              Map.of(
                  "session_key",
                  "claude_code:rounds",
                  "session_id",
                  "rounds",
                  "assistantMessageCount",
                  7),
              List.of(
                  makeCallWithTurn("c1", 1, "turn", List.of(), List.of()),
                  makeCallWithTurn("c2", 2, "turn", List.of(), List.of())),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      var row =
          com.feipi.session.browser.index.store.sqlite.mapper.ArtifactRowMapper.toSessionRow(
              artifact, 0, "fixture");
      var detail =
          SessionDetailAssembler.assemble(
              row, artifact, PayloadVisibility.STANDARD, "fixture.json", 3);
      assertThat(row.roundCount()).isEqualTo((long) detail.rounds().size()).isEqualTo(1L);
      assertThat(row.llmCallCount()).isEqualTo(2L);
      assertThat(row.assistantMessageCount()).isEqualTo(7L);
    }

    @Test
    @DisplayName("无制品的装配生成空轮次和 payload")
    void assembleWithoutArtifact() {
      NormalizedSessionArtifact artifact = makeEmptyArtifact();
      SessionDetail detail =
          SessionDetailAssembler.assemble(
              TEST_ROW, artifact, PayloadVisibility.STANDARD, "/art/test.json", 1);
      assertThat(detail.sessionRow()).isEqualTo(TEST_ROW);
      assertThat(detail.visibility()).isEqualTo(PayloadVisibility.STANDARD);
      assertThat(detail.artifactPath()).isEqualTo("/art/test.json");
      assertThat(detail.hasArtifact()).isTrue();
    }
  }

  @Test
  void contentLargerThanLegacyLimitKeepsExactCountsWithoutMaterializingLists() throws Exception {
    var calls =
        java.util.stream.IntStream.rangeClosed(1, 10_001)
            .mapToObj(i -> makeCallWithTurn("large-" + i, i, "one-turn", List.of(), List.of()))
            .toList();
    var empty =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
            makeEmptyArtifact());
    var content =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromLists(
            new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
                empty.header().schemaVersion(),
                empty.header().agent(),
                empty.header().session(),
                Map.of(
                    "calls",
                    10_001L,
                    "toolExecutions",
                    0L,
                    "diagnostics",
                    0L,
                    "sourceFiles",
                    0L,
                    "sourceUnitCatalog",
                    0L,
                    "sourceUnitSequenceEntries",
                    0L)),
            List.of(),
            calls,
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var detail =
        SessionDetailAssembler.assemble(
            TEST_ROW, content, PayloadVisibility.STANDARD, "large.json", 3);
    assertThat(detail.hasArtifact()).isTrue();
    assertThat(detail.roundCount()).isEqualTo(1);
    assertThat(detail.payloadSourceCount()).isEqualTo(20_002);
    assertThat(detail.rounds()).isEmpty();
    assertThat(detail.payloadSources()).isEmpty();
    var reader = new SessionContentReader(content, TEST_ROW.userMessageCount());
    var tail = reader.calls(1, 10_000L, 500);
    assertThat(tail.total()).isEqualTo(10_001);
    assertThat(tail.items()).extracting(NormalizedCall::callId).containsExactly("large-10001");
    assertThat(tail.nextCursor()).isNull();
    var first = reader.calls(1, 0, 500);
    assertThat(first.items()).hasSize(500);
    assertThat(first.nextCursor()).isEqualTo(500L);
    assertThat(reader.findCall("large-10001")).isPresent();
    var payloadTail = reader.payloadSources(PayloadVisibility.STANDARD, 20_000L, 500);
    assertThat(payloadTail.total()).isEqualTo(20_002);
    assertThat(payloadTail.items()).hasSize(2);
    assertThat(payloadTail.nextCursor()).isNull();
  }

  @Test
  void legacyReaderDefaultOpenRemainsReplayable() throws Exception {
    NormalizedArtifactReader reader = ignored -> makeEmptyArtifact();
    var content = reader.open(java.nio.file.Path.of("synthetic.json"));
    assertThat(content.toArtifact()).isEqualTo(makeEmptyArtifact());
    assertThat(content.toArtifact()).isEqualTo(makeEmptyArtifact());
  }

  @Test
  void smallTotalsStreamContentMustNotBeFlattenedByAssembler() throws Exception {
    var content = streamOnlySmallContent();
    var detail =
        SessionDetailAssembler.assemble(
            TEST_ROW, content, PayloadVisibility.STANDARD, "stream-only.json", 3);
    assertThat(detail.roundCount()).isEqualTo(1);
    assertThat(detail.payloadSourceCount()).isEqualTo(2);
    assertThat(detail.rounds()).isEmpty();
  }

  @Test
  void smallTotalsStreamContentMustNotBeFlattenedByUseCase() throws Exception {
    var content = streamOnlySmallContent();
    var artifactRow =
        new com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow(
            TEST_ROW.sessionKey(),
            "normalized",
            "stream-only.json",
            NormalizedConstants.SCHEMA_VERSION,
            "synthetic.jsonl",
            0,
            1,
            0,
            0);
    var port =
        new com.feipi.session.browser.index.api.query.SessionDetailPort() {
          public Optional<com.feipi.session.browser.index.api.query.SessionRecord> findSession(
              String key) {
            return Optional.of(TEST_ROW);
          }

          public List<com.feipi.session.browser.index.api.query.SessionArtifactRecord>
              findArtifacts(String key) {
            return List.of(artifactRow);
          }

          public Optional<com.feipi.session.browser.index.api.query.SessionArtifactRecord>
              findNormalizedArtifact(String key) {
            return Optional.of(artifactRow);
          }
        };
    var reader =
        new NormalizedArtifactReader() {
          public NormalizedSessionArtifact load(java.nio.file.Path path) {
            throw new AssertionError("stream-only content must be opened, not loaded");
          }

          public com.feipi.session.browser.domain.normalized.NormalizedSessionContent open(
              java.nio.file.Path path) {
            return content;
          }
        };
    var context =
        new com.feipi.session.browser.application.SessionDetailUseCase(port, reader, 3)
            .getDetailContext(TEST_ROW.sessionKey(), PayloadVisibility.STANDARD)
            .orElseThrow();
    assertThat(context.artifact()).isNull();
    assertThat(context.content()).isSameAs(content);
    assertThat(context.detail().roundCount()).isEqualTo(1);
    assertThat(context.detail().payloadSourceCount()).isEqualTo(2);
  }

  private static com.feipi.session.browser.domain.normalized.NormalizedSessionContent
      streamOnlySmallContent() {
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            Map.of(),
            List.of(makeCall("stream-1", 1, CallScope.MAIN, Optional.empty())),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var delegate =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(artifact);
    return new com.feipi.session.browser.domain.normalized.NormalizedSessionContent() {
      public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
        return delegate.header();
      }

      public ContentCursor openCursor() throws java.io.IOException {
        return delegate.openCursor();
      }

      public NormalizedSessionArtifact toArtifact() {
        throw new AssertionError("small totals are not proof of an existing legacy artifact");
      }
    };
  }

  private static NormalizedCall makeCall(
      String callId, int callIndex, CallScope scope, Optional<String> parentCallId) {
    return makeCall(callId, callIndex, scope, parentCallId, NormalizedCallUsage.empty());
  }

  private static NormalizedCall makeCall(
      String callId,
      int callIndex,
      CallScope scope,
      Optional<String> parentCallId,
      NormalizedCallUsage usage) {
    return new NormalizedCall(
        callId,
        callIndex,
        "C" + callIndex,
        scope,
        parentCallId,
        Optional.empty(),
        Optional.empty(),
        "claude-3",
        Optional.empty(),
        usage,
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall makeCallWithTurn(
      String callId,
      int callIndex,
      String turnId,
      List<String> toolResultIds,
      List<String> toolCallIds) {
    return new NormalizedCall(
        callId,
        callIndex,
        "C" + callIndex,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of(turnId),
        "claude-3",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        new NormalizedCallRequest(toolResultIds),
        new NormalizedCallResponse(toolCallIds),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedToolExecution makeToolExecution(
      String toolCallId, String declaredByCallId, Optional<String> status) {
    return new NormalizedToolExecution(
        toolCallId,
        "tool",
        CallScope.MAIN,
        declaredByCallId,
        Optional.empty(),
        status,
        Optional.empty(),
        1,
        List.of(),
        Optional.empty());
  }

  private static NormalizedSessionArtifact makeEmptyArtifact() {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", "cc:s1"),
        List.of(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
