package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link CallBuilder} 单元测试。
 *
 * <p>验证从分类事件构建 NormalizedCall 和 NormalizedToolExecution 的逻辑，包括 callId 生成、 工具调用提取和
 * tool_use/tool_result 关联。
 */
@DisplayName("CallBuilder 调用构建器测试")
class CallBuilderTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Nested
  @DisplayName("buildCalls")
  class BuildCallsTests {

    @Test
    @DisplayName("空分类返回空调用列表")
    void emptyClassifiedReturnsEmptyCalls() {
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of());

      List<NormalizedCall> calls = CallBuilder.buildCalls(List.of(), classified);

      assertThat(calls).isEmpty();
    }

    @Test
    @DisplayName("单个 assistant 消息构建单个调用")
    void singleAssistantMessageBuildsSingleCall() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");
      event.put("model", "claude-3-sonnet");

      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of(event));

      List<NormalizedCall> calls = CallBuilder.buildCalls(List.of(event), classified);

      assertThat(calls).hasSize(1);
      NormalizedCall call = calls.get(0);
      assertThat(call.callId()).isEqualTo("call-1");
      assertThat(call.callIndex()).isEqualTo(1);
      assertThat(call.callKey()).isEqualTo("C1");
      assertThat(call.scope()).isEqualTo(CallScope.MAIN);
      assertThat(call.model()).isEqualTo("claude-3-sonnet");
    }

    @Test
    @DisplayName("callKey 与 callIndex 一致")
    void callKeyMatchesCallIndex() {
      List<JsonNode> events =
          List.of(assistantEvent("call-a", "model-x"), assistantEvent("call-b", "model-y"));

      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);

      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      assertThat(calls).hasSize(2);
      assertThat(calls.get(0).callIndex()).isEqualTo(1);
      assertThat(calls.get(0).callKey()).isEqualTo("C1");
      assertThat(calls.get(1).callIndex()).isEqualTo(2);
      assertThat(calls.get(1).callKey()).isEqualTo("C2");
    }

    @Test
    @DisplayName("无 id 字段时使用 C{index} 作为 callId")
    void noIdFieldUsesFallbackCallId() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");

      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of(event));

      List<NormalizedCall> calls = CallBuilder.buildCalls(List.of(event), classified);

      assertThat(calls).hasSize(1);
      assertThat(calls.get(0).callId()).isEqualTo("C1");
    }

    @Test
    @DisplayName("从 content 中提取 tool_use 块到 response.toolCallIds")
    void extractsToolUseFromContent() {
      ObjectNode event = createAssistantWithToolUse("call-1", "toolu_1", "Read");

      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of(event));

      List<NormalizedCall> calls = CallBuilder.buildCalls(List.of(event), classified);

      assertThat(calls).hasSize(1);
      assertThat(calls.get(0).response().toolCallIds()).containsExactly("toolu_1");
    }

    @Test
    @DisplayName("tool_result 分配给后续 assistant 调用")
    void toolResultAssignedToNextAssistantCall() {
      // 助手调用后返回工具结果，再传递给下一个助手调用
      ObjectNode assistant1 = createAssistantWithToolUse("C1", "toolu_1", "Read");
      ObjectNode toolResult =
          MAPPER.createObjectNode().put("type", "tool_result").put("tool_use_id", "toolu_1");
      ObjectNode assistant2 = assistantEvent("C2", "model-x");

      List<JsonNode> events = List.of(assistant1, toolResult, assistant2);
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);

      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      assertThat(calls).hasSize(2);
      // tool_result 被分配给 C2（下一个助手调用）
      assertThat(calls.get(1).request().toolResultIds()).containsExactly("toolu_1");
      // C1 不消费任何 tool_result
      assertThat(calls.get(0).request().toolResultIds()).isEmpty();
    }

    @Test
    @DisplayName("tool_result 在最后无后续 assistant 时分配给最后一个调用")
    void toolResultWithoutFollowingAssistantGoesToLastCall() {
      ObjectNode assistant1 = createAssistantWithToolUse("C1", "toolu_1", "Read");
      ObjectNode toolResult =
          MAPPER.createObjectNode().put("type", "tool_result").put("tool_use_id", "toolu_1");

      List<JsonNode> events = List.of(assistant1, toolResult);
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);

      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      assertThat(calls).hasSize(1);
      // 无后续助手调用，tool_result 归因于最后一个调用
      assertThat(calls.get(0).request().toolResultIds()).containsExactly("toolu_1");
    }

    @Test
    @DisplayName("usage 从事件中提取")
    void usageExtractedFromEvent() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");
      ObjectNode usage = event.putObject("usage");
      usage.put("input_tokens", 100);
      usage.put("output_tokens", 200);
      usage.put("cache_read_input_tokens", 50);

      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of(event));

      List<NormalizedCall> calls = CallBuilder.buildCalls(List.of(event), classified);

      assertThat(calls.get(0).usage().fresh()).isEqualTo(100);
      assertThat(calls.get(0).usage().output()).isEqualTo(200);
      assertThat(calls.get(0).usage().cacheRead()).isEqualTo(50);
      assertThat(calls.get(0).usage().total()).isEqualTo(350);
    }
  }

  @Nested
  @DisplayName("buildToolExecutions")
  class BuildToolExecutionsTests {

    @Test
    @DisplayName("assistant 中的 tool_use 生成工具执行边")
    void toolUseInAssistantGeneratesExecution() {
      ObjectNode event = createAssistantWithToolUse("call-1", "toolu_abc", "Read");

      List<JsonNode> events = List.of(event);
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);
      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      List<NormalizedToolExecution> executions =
          CallBuilder.buildToolExecutions(events, classified, calls);

      assertThat(executions).hasSize(1);
      NormalizedToolExecution exec = executions.get(0);
      assertThat(exec.toolCallId()).isEqualTo("toolu_abc");
      assertThat(exec.name()).isEqualTo("Read");
      assertThat(exec.scope()).isEqualTo(CallScope.MAIN);
      assertThat(exec.declaredByCallId()).isEqualTo("call-1");
      // 没有 tool_result，所以 resultConsumedByCallId 为空
      assertThat(exec.resultConsumedByCallId()).isEmpty();
    }

    @Test
    @DisplayName("tool_use + tool_result 正确关联")
    void toolUseAndToolResultCorrectlyLinked() {
      ObjectNode assistant1 = createAssistantWithToolUse("C1", "toolu_1", "Read");
      ObjectNode toolResult =
          MAPPER.createObjectNode().put("type", "tool_result").put("tool_use_id", "toolu_1");
      ObjectNode assistant2 = assistantEvent("C2", "model-x");

      List<JsonNode> events = List.of(assistant1, toolResult, assistant2);
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);
      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      List<NormalizedToolExecution> executions =
          CallBuilder.buildToolExecutions(events, classified, calls);

      assertThat(executions).hasSize(1);
      NormalizedToolExecution exec = executions.get(0);
      assertThat(exec.toolCallId()).isEqualTo("toolu_1");
      assertThat(exec.declaredByCallId()).isEqualTo("C1");
      // tool_result 被 C2 消费
      assertThat(exec.resultConsumedByCallId()).hasValue("C2");
    }

    @Test
    @DisplayName("独立 tool_use 事件生成工具执行边")
    void standaloneToolUseGeneratesExecution() {
      ObjectNode assistant = assistantEvent("C1", "model-x");
      ObjectNode standaloneToolUse =
          MAPPER
              .createObjectNode()
              .put("type", "tool_use")
              .put("id", "toolu_standalone")
              .put("name", "Write");

      List<JsonNode> events = List.of(assistant, standaloneToolUse);
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);
      List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

      List<NormalizedToolExecution> executions =
          CallBuilder.buildToolExecutions(events, classified, calls);

      assertThat(executions).hasSize(1);
      assertThat(executions.get(0).toolCallId()).isEqualTo("toolu_standalone");
      assertThat(executions.get(0).name()).isEqualTo("Write");
    }

    @Test
    @DisplayName("无 assistant 消息时返回空列表")
    void noAssistantReturnsEmpty() {
      EventClassifier.ClassifiedEvents classified = EventClassifier.classify(List.of());

      List<NormalizedToolExecution> executions =
          CallBuilder.buildToolExecutions(List.of(), classified, List.of());

      assertThat(executions).isEmpty();
    }
  }

  // --- 辅助方法 ---

  private static ObjectNode assistantEvent(String id, String model) {
    ObjectNode event = MAPPER.createObjectNode();
    event.put("type", "assistant");
    event.put("id", id);
    event.put("model", model);
    return event;
  }

  private static ObjectNode createAssistantWithToolUse(
      String callId, String toolUseId, String toolName) {
    ObjectNode event = MAPPER.createObjectNode();
    event.put("type", "assistant");
    event.put("id", callId);
    event.put("model", "claude-3-sonnet");
    ArrayNode content = event.putArray("content");
    ObjectNode toolUse = content.addObject();
    toolUse.put("type", "tool_use");
    toolUse.put("id", toolUseId);
    toolUse.put("name", toolName);
    return event;
  }
}
