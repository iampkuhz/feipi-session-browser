package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
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
    @DisplayName("子 agent 调用合并到父调用轮次")
    void subagentCallMergedToParent() {
      NormalizedCall mainCall = makeCall("c1", 1, CallScope.MAIN, Optional.empty());
      NormalizedCall subCall = makeCall("c2", 2, CallScope.SUBAGENT, Optional.of("c1"));
      List<CallRound> rounds = SessionDetailAssembler.buildRounds(List.of(mainCall, subCall));
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).calls()).containsExactly("c1", "c2");
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
      assertThat(sources.get(0).truncated()).isTrue();
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

  private static NormalizedCall makeCall(
      String callId, int callIndex, CallScope scope, Optional<String> parentCallId) {
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
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
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
