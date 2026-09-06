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
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link PayloadLookup} 测试。
 *
 * <p>覆盖 payload 查找表的构建、查询、敏感字段 masking 和可见性策略。
 */
@DisplayName("PayloadLookup 测试")
class PayloadLookupTest {

  @Nested
  @DisplayName("fromArtifact 构建")
  class FromArtifact {

    @Test
    @DisplayName("空制品生成空查找表")
    void emptyArtifact() {
      NormalizedSessionArtifact artifact = makeArtifact(List.of());
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      assertThat(lookup.size()).isZero();
      assertThat(lookup.allPayloadIds()).isEmpty();
    }

    @Test
    @DisplayName("每次调用生成请求和响应条目")
    void callGeneratesEntries() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      assertThat(lookup.size()).isEqualTo(2);
      assertThat(lookup.allPayloadIds()).containsExactly("main:req:c1", "main:resp:c1");
    }

    @Test
    @DisplayName("标准可见性标记截断")
    void standardVisibilityTruncated() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().truncated()).isTrue();
    }

    @Test
    @DisplayName("完整可见性不截断")
    void fullVisibilityNotTruncated() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().truncated()).isFalse();
    }
  }

  @Nested
  @DisplayName("lookup 查询")
  class Lookup {

    @Test
    @DisplayName("存在的 payload 返回条目")
    void existingPayload() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().kind()).isEqualTo(PayloadSourceKind.LLM_REQUEST);
      assertThat(entry.get().callId()).isEqualTo("c1");
    }

    @Test
    @DisplayName("不存在的 payload 返回 empty")
    void missingPayload() {
      NormalizedSessionArtifact artifact = makeArtifact(List.of());
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      assertThat(lookup.lookup("missing")).isEmpty();
    }
  }

  @Nested
  @DisplayName("lookupByCallId 查询")
  class LookupByCallId {

    @Test
    @DisplayName("按 callId 返回全部关联条目")
    void byCallId() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
      var entries = lookup.lookupByCallId("c1");
      assertThat(entries).hasSize(2);
    }

    @Test
    @DisplayName("不匹配的 callId 返回空列表")
    void noMatch() {
      NormalizedSessionArtifact artifact = makeArtifact(List.of());
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      assertThat(lookup.lookupByCallId("missing")).isEmpty();
    }
  }

  @Nested
  @DisplayName("Payload 条目内容")
  class PayloadEntryContent {

    @Test
    @DisplayName("标准可见性下条目标记为截断")
    void standardVisibilityTruncated() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().truncated()).isTrue();
    }

    @Test
    @DisplayName("完整可见性下条目不截断")
    void fullVisibilityNotTruncated() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().truncated()).isFalse();
    }
  }

  @Nested
  @DisplayName("Payload 内容提取")
  class PayloadContentExtraction {

    @Test
    @DisplayName("sourceUnits 有内容时 request 条目包含提取的文本")
    void requestContentExtracted() {
      Map<String, Object> userUnit =
          Map.of("role", "user", "type", "text", "text", "Analyze this file");
      NormalizedCall call = makeCallWithUnits("c1", List.of(userUnit));
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      var entry = lookup.lookup("main:req:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().content()).isEqualTo("Analyze this file");
    }

    @Test
    @DisplayName("sourceUnits 有内容时 response 条目包含提取的文本")
    void responseContentExtracted() {
      Map<String, Object> assistantUnit =
          Map.of("role", "assistant", "type", "text", "text", "Here is the analysis");
      NormalizedCall call = makeCallWithUnits("c1", List.of(assistantUnit));
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      var entry = lookup.lookup("main:resp:c1");
      assertThat(entry).isPresent();
      assertThat(entry.get().content()).isEqualTo("Here is the analysis");
    }

    @Test
    @DisplayName("sourceUnits 为空时 content 为空字符串")
    void emptyContentWhenNoSourceUnits() {
      NormalizedCall call = makeCall("c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      assertThat(lookup.lookup("main:req:c1").get().content()).isEmpty();
      assertThat(lookup.lookup("main:resp:c1").get().content()).isEmpty();
    }

    @Test
    @DisplayName("工具执行生成 tool:result payload 条目")
    void toolResultEntryCreated() {
      Map<String, Object> toolResultUnit =
          Map.of(
              "role", "user",
              "type", "tool_result",
              "tool_call_id", "tool-001",
              "content", "File contents here");
      NormalizedCall call = makeCallWithUnits("c2", List.of(toolResultUnit));
      var exec =
          new NormalizedToolExecution(
              "tool-001",
              "Read",
              CallScope.MAIN,
              "c1",
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              100L,
              List.of(),
              Optional.empty());
      NormalizedSessionArtifact artifact =
          new NormalizedSessionArtifact(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CLAUDE_CODE,
              List.of(),
              Map.of("session_key", "cc:s1"),
              List.of(call),
              List.of(exec),
              List.of(),
              Map.of(),
              Map.of());
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      var entry = lookup.lookup("tool:result:tool-001");
      assertThat(entry).isPresent();
      assertThat(entry.get().content()).isEqualTo("File contents here");
      assertThat(entry.get().kind()).isEqualTo(PayloadSourceKind.TOOL_RESULT);
    }

    @Test
    @DisplayName("subagent 调用使用 sa 前缀")
    void subagentPrefix() {
      Map<String, Object> assistantUnit =
          Map.of("role", "assistant", "type", "text", "text", "Subagent response");
      NormalizedCall call =
          new NormalizedCall(
              "sc1",
              1,
              "C1",
              CallScope.SUBAGENT,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              new NormalizedCallUsage(50, 30, 20, 100, 200),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(assistantUnit),
              Map.of(),
              Map.of());
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      assertThat(lookup.allPayloadIds()).contains("sa:req:sc1", "sa:resp:sc1");
      assertThat(lookup.lookup("sa:resp:sc1").get().content()).isEqualTo("Subagent response");
    }
  }

  private static NormalizedCall makeCall(String callId) {
    return new NormalizedCall(
        callId,
        1,
        "C1",
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "claude-3",
        Optional.empty(),
        new NormalizedCallUsage(50, 30, 20, 100, 200),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall makeCallWithUnits(
      String callId, List<Map<String, Object>> sourceUnits) {
    return new NormalizedCall(
        callId,
        1,
        "C1",
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "claude-3",
        Optional.empty(),
        new NormalizedCallUsage(50, 30, 20, 100, 200),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        sourceUnits,
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionArtifact makeArtifact(List<NormalizedCall> calls) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", "cc:s1"),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionArtifact makeArtifactWithCalls(List<NormalizedCall> calls) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", "cc:s1"),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
