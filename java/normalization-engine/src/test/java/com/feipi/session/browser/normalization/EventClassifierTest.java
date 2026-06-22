package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link EventClassifier} 单元测试。
 *
 * <p>验证事件按 {@code type} 字段的分类逻辑，包括标准类型和未知类型处理。
 */
@DisplayName("EventClassifier 事件分类器测试")
class EventClassifierTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Nested
  @DisplayName("classify")
  class ClassifyTests {

    @Test
    @DisplayName("空列表返回所有类别为空")
    void emptyListReturnsAllEmpty() {
      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of());

      assertThat(result.assistantMessages()).isEmpty();
      assertThat(result.toolUses()).isEmpty();
      assertThat(result.toolResults()).isEmpty();
      assertThat(result.userMessages()).isEmpty();
      assertThat(result.unknownEvents()).isEmpty();
      assertThat(result.isEmpty()).isTrue();
      assertThat(result.totalCount()).isZero();
    }

    @Test
    @DisplayName("null 列表返回所有类别为空")
    void nullListReturnsAllEmpty() {
      EventClassifier.ClassifiedEvents result = EventClassifier.classify(null);

      assertThat(result.isEmpty()).isTrue();
    }

    @Test
    @DisplayName("assistant 类型事件正确分类")
    void assistantEventClassifiedCorrectly() {
      JsonNode event = MAPPER.createObjectNode().put("type", "assistant");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.assistantMessages()).hasSize(1);
      assertThat(result.assistantMessages().get(0)).isEqualTo(event);
      assertThat(result.totalCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("tool_use 类型事件正确分类")
    void toolUseEventClassifiedCorrectly() {
      JsonNode event =
          MAPPER
              .createObjectNode()
              .put("type", "tool_use")
              .put("id", "toolu_abc")
              .put("name", "Read");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.toolUses()).hasSize(1);
      assertThat(result.toolUses().get(0)).isEqualTo(event);
    }

    @Test
    @DisplayName("tool_result 类型事件正确分类")
    void toolResultEventClassifiedCorrectly() {
      JsonNode event =
          MAPPER.createObjectNode().put("type", "tool_result").put("tool_use_id", "toolu_abc");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.toolResults()).hasSize(1);
    }

    @Test
    @DisplayName("user 类型事件正确分类")
    void userEventClassifiedCorrectly() {
      JsonNode event = MAPPER.createObjectNode().put("type", "user");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.userMessages()).hasSize(1);
    }

    @Test
    @DisplayName("未知类型事件进入 unknownEvents")
    void unknownTypeGoesToUnknownEvents() {
      JsonNode event = MAPPER.createObjectNode().put("type", "system_status");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.unknownEvents()).hasSize(1);
      assertThat(result.unknownEvents().get(0)).isEqualTo(event);
      assertThat(result.assistantMessages()).isEmpty();
    }

    @Test
    @DisplayName("缺少 type 字段的事件进入 unknownEvents")
    void missingTypeFieldGoesToUnknownEvents() {
      JsonNode event = MAPPER.createObjectNode().put("data", "some value");

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(event));

      assertThat(result.unknownEvents()).hasSize(1);
    }

    @Test
    @DisplayName("混合事件正确分类到各类别")
    void mixedEventsClassifiedCorrectly() {
      List<JsonNode> events =
          List.of(
              MAPPER.createObjectNode().put("type", "assistant"),
              MAPPER.createObjectNode().put("type", "tool_result").put("tool_use_id", "t1"),
              MAPPER.createObjectNode().put("type", "user"),
              MAPPER.createObjectNode().put("type", "unknown_type"),
              MAPPER.createObjectNode().put("type", "assistant"));

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(events);

      assertThat(result.assistantMessages()).hasSize(2);
      assertThat(result.toolResults()).hasSize(1);
      assertThat(result.userMessages()).hasSize(1);
      assertThat(result.unknownEvents()).hasSize(1);
      assertThat(result.totalCount()).isEqualTo(5);
      assertThat(result.isEmpty()).isFalse();
    }

    @Test
    @DisplayName("allEvents 返回所有分类事件的汇总")
    void allEventsReturnsCombinedList() {
      List<JsonNode> events =
          List.of(
              MAPPER.createObjectNode().put("type", "assistant"),
              MAPPER.createObjectNode().put("type", "user"));

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(events);

      assertThat(result.allEvents()).hasSize(2);
    }

    @Test
    @DisplayName("null 事件被跳过")
    void nullEventsAreSkipped() {
      List<JsonNode> events = new java.util.ArrayList<>();
      events.add(null);
      events.add(MAPPER.createObjectNode().put("type", "assistant"));

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(events);

      assertThat(result.assistantMessages()).hasSize(1);
      assertThat(result.totalCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("非对象事件进入 unknownEvents")
    void nonObjectEventsGoToUnknown() {
      JsonNode arrayNode = MAPPER.createArrayNode();

      EventClassifier.ClassifiedEvents result = EventClassifier.classify(List.of(arrayNode));

      assertThat(result.unknownEvents()).hasSize(1);
    }
  }
}
