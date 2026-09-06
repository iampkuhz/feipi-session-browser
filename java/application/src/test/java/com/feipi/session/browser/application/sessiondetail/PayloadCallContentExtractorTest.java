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
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

@DisplayName("PayloadCallContentExtractor 测试")
class PayloadCallContentExtractorTest {

  @Nested
  @DisplayName("内联 sourceUnits 提取")
  class InlineSourceUnits {

    @Test
    @DisplayName("从 assistant sourceUnits 提取 response 文本")
    void extractsResponseText() {
      Map<String, Object> assistantUnit =
          Map.of("role", "assistant", "type", "text", "text", "Hello, world!");
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(assistantUnit));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      String content = PayloadCallContentExtractor.extractResponseContent(call, artifact);

      assertThat(content).isEqualTo("Hello, world!");
    }

    @Test
    @DisplayName("从 user sourceUnits 提取 request 文本")
    void extractsRequestText() {
      Map<String, Object> userUnit =
          Map.of("role", "user", "type", "text", "text", "Please analyze this.");
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(userUnit));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      String content = PayloadCallContentExtractor.extractRequestContent(call, artifact);

      assertThat(content).isEqualTo("Please analyze this.");
    }

    @Test
    @DisplayName("合并多个同 role 文本块")
    void mergesMultipleTextBlocks() {
      Map<String, Object> block1 = Map.of("role", "assistant", "type", "text", "text", "Part 1");
      Map<String, Object> block2 = Map.of("role", "assistant", "type", "text", "text", "Part 2");
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(block1, block2));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      String content = PayloadCallContentExtractor.extractResponseContent(call, artifact);

      assertThat(content).isEqualTo("Part 1\nPart 2");
    }

    @Test
    @DisplayName("从 content list 提取文本")
    void extractsFromContentList() {
      List<Map<String, Object>> contentBlocks =
          List.of(
              Map.of("type", "text", "text", "Block A"), Map.of("type", "text", "text", "Block B"));
      Map<String, Object> unit = Map.of("role", "assistant", "content", contentBlocks);
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(unit));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      String content = PayloadCallContentExtractor.extractResponseContent(call, artifact);

      assertThat(content).isEqualTo("Block A\nBlock B");
    }

    @Test
    @DisplayName("无匹配 sourceUnits 返回空字符串")
    void returnsEmptyWhenNoMatch() {
      Map<String, Object> userUnit = Map.of("role", "user", "type", "text", "text", "user input");
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(userUnit));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      String content = PayloadCallContentExtractor.extractResponseContent(call, artifact);

      assertThat(content).isEmpty();
    }

    @Test
    @DisplayName("空 sourceUnits 返回空字符串")
    void returnsEmptyForEmptySourceUnits() {
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of());
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      assertThat(PayloadCallContentExtractor.extractRequestContent(call, artifact)).isEmpty();
      assertThat(PayloadCallContentExtractor.extractResponseContent(call, artifact)).isEmpty();
    }
  }

  @Nested
  @DisplayName("工具结果提取")
  class ToolResultExtraction {

    @Test
    @DisplayName("从 sourceUnits 提取 tool_result 内容")
    void extractsToolResultFromSourceUnits() {
      Map<String, Object> toolResultUnit =
          Map.of(
              "role", "user",
              "type", "tool_result",
              "tool_call_id", "tool-001",
              "content", "File contents here");
      NormalizedCall call = makeCallWithSourceUnits("c2", List.of(toolResultUnit));
      NormalizedToolExecution exec = makeToolExecution("tool-001", "Read", "c1");
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of(exec));

      Map<String, String> results = PayloadCallContentExtractor.extractToolResultContents(artifact);

      assertThat(results).containsEntry("tool-001", "File contents here");
    }

    @Test
    @DisplayName("无工具结果时返回空映射")
    void returnsEmptyMapWhenNoResults() {
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of());
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      Map<String, String> results = PayloadCallContentExtractor.extractToolResultContents(artifact);

      assertThat(results).isEmpty();
    }
  }

  @Nested
  @DisplayName("assistant 文本映射")
  class AssistantTextMap {

    @Test
    @DisplayName("构建 callId 到 assistant 文本的映射")
    void buildsCallAssistantTextMap() {
      Map<String, Object> unit1 =
          Map.of("role", "assistant", "type", "text", "text", "First response");
      Map<String, Object> unit2 =
          Map.of("role", "assistant", "type", "text", "text", "Second response");
      NormalizedCall call1 = makeCallWithSourceUnits("c1", List.of(unit1));
      NormalizedCall call2 = makeCallWithSourceUnits("c2", List.of(unit2));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call1, call2), List.of());

      Map<String, String> texts =
          PayloadCallContentExtractor.buildCallAssistantTextMap(artifact.calls(), artifact);

      assertThat(texts)
          .containsEntry("c1", "First response")
          .containsEntry("c2", "Second response");
    }

    @Test
    @DisplayName("跳过无 assistant 文本的调用")
    void skipsCallsWithoutAssistantText() {
      Map<String, Object> userUnit = Map.of("role", "user", "type", "text", "text", "input");
      NormalizedCall call = makeCallWithSourceUnits("c1", List.of(userUnit));
      NormalizedSessionArtifact artifact = makeArtifact(List.of(call), List.of());

      Map<String, String> texts =
          PayloadCallContentExtractor.buildCallAssistantTextMap(artifact.calls(), artifact);

      assertThat(texts).doesNotContainKey("c1");
    }
  }

  private static NormalizedCall makeCallWithSourceUnits(
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

  private static NormalizedToolExecution makeToolExecution(
      String toolCallId, String name, String declaredByCallId) {
    return new NormalizedToolExecution(
        toolCallId,
        name,
        CallScope.MAIN,
        declaredByCallId,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        100L,
        List.of(),
        Optional.empty());
  }

  private static NormalizedSessionArtifact makeArtifact(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", "cc:s1"),
        calls,
        toolExecutions,
        List.of(),
        Map.of(),
        Map.of());
  }
}
