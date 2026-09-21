package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

@DisplayName("QoderResponseRecords 合并测试")
class QoderResponseRecordsTest {

  @Test
  @DisplayName("同 responseMessageId 连续 assistant 分片合并为单条记录")
  void consecutiveAssistantWithSameResponseMessageIdMerge() {
    var records =
        List.of(
            assistantWithMeta("msg-1", null, "I will inspect", List.of()),
            assistantWithMeta(
                "msg-1", null, "", List.of(toolCall("t1", "Read", "{\"file_path\":\"/a.md\"}"))),
            assistantWithMeta(
                "msg-1",
                "tool_use",
                "",
                List.of(toolCall("t2", "Read", "{\"file_path\":\"/b.md\"}"))));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(1);
    assertThat(merged.get(0).content()).isEqualTo("I will inspect");
    assertThat(merged.get(0).toolCalls()).hasSize(2);
    assertThat(merged.get(0).toolCalls())
        .extracting(SourceToolCall::toolCallId)
        .containsExactly("t1", "t2");
    assertThat(merged.get(0).toolCalls())
        .extracting(SourceToolCall::name)
        .containsExactly("Read", "Read");
    assertThat(merged.get(0).toolCalls().get(0).input()).isEqualTo("{\"file_path\":\"/a.md\"}");
  }

  @Test
  @DisplayName("不同 responseMessageId 的 assistant 不合并")
  void differentResponseMessageIdsDoNotMerge() {
    var records =
        List.of(
            assistantWithMeta("msg-1", null, "first", List.of()),
            assistantWithMeta("msg-2", null, "second", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(2);
    assertThat(merged.get(0).content()).isEqualTo("first");
    assertThat(merged.get(1).content()).isEqualTo("second");
  }

  @Test
  @DisplayName("user/tool_result 边界阻止合并")
  void userAndToolResultBoundariesPreventMerge() {
    var records =
        List.of(
            assistantWithMeta("msg-1", "tool_use", "first", List.of(toolCall("t1", "Read", ""))),
            toolResult("t1"),
            assistantWithMeta("msg-1", null, "second", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(3);
    assertThat(merged.get(0).content()).isEqualTo("first");
    assertThat(merged.get(0).toolCalls()).hasSize(1);
    assertThat(merged.get(1).eventType()).isEqualTo("tool_result");
    assertThat(merged.get(2).content()).isEqualTo("second");
  }

  @Test
  @DisplayName("stop_reason 终止合并，后续同 message.id 不并入前响应")
  void stopReasonTerminatesMerge() {
    var records =
        List.of(
            assistantWithMeta("msg-1", "tool_use", "first", List.of(toolCall("t1", "Read", ""))),
            assistantWithMeta("msg-1", "end_turn", "second", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(2);
    assertThat(merged.get(0).content()).isEqualTo("first");
    assertThat(merged.get(0).responseStopReason()).contains("tool_use");
    assertThat(merged.get(1).content()).isEqualTo("second");
    assertThat(merged.get(1).responseStopReason()).contains("end_turn");
  }

  @Test
  @DisplayName("重复 toolCallId：首片 input 空、后续完整时保留完整参数")
  void duplicateToolCallIdKeepsCompleteInput() {
    var records =
        List.of(
            assistantWithMeta("msg-1", null, "", List.of(toolCall("t1", "Read", ""))),
            assistantWithMeta(
                "msg-1",
                null,
                "",
                List.of(toolCall("t1", "Read", "{\"file_path\":\"/complete.md\"}"))));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(1);
    assertThat(merged.get(0).toolCalls()).hasSize(1);
    assertThat(merged.get(0).toolCalls().get(0).input())
        .isEqualTo("{\"file_path\":\"/complete.md\"}");
  }

  @Test
  @DisplayName("重复 toolCallId：首片有 input 时保留首片")
  void duplicateToolCallIdKeepsFirstNonEmptyInput() {
    var records =
        List.of(
            assistantWithMeta(
                "msg-1",
                null,
                "",
                List.of(toolCall("t1", "Read", "{\"file_path\":\"/first.md\"}"))),
            assistantWithMeta(
                "msg-1",
                null,
                "",
                List.of(toolCall("t1", "Read", "{\"file_path\":\"/stale.md\"}"))));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(1);
    assertThat(merged.get(0).toolCalls()).hasSize(1);
    assertThat(merged.get(0).toolCalls().get(0).input()).isEqualTo("{\"file_path\":\"/first.md\"}");
  }

  @Test
  @DisplayName("无 responseMessageId 的 assistant 不参与合并")
  void assistantWithoutResponseMessageIdDoesNotMerge() {
    var records =
        List.of(
            assistantWithMeta(null, null, "no-id-1", List.of()),
            assistantWithMeta(null, null, "no-id-2", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(2);
  }

  @Test
  @DisplayName("空列表和单元素列表不变")
  void emptyAndSingleElementListsUnchanged() {
    assertThat(QoderResponseRecords.merge(List.of())).isEmpty();
    var single = List.of(assistantWithMeta("msg-1", null, "only", List.of()));
    assertThat(QoderResponseRecords.merge(single)).hasSize(1);
  }

  @Test
  @DisplayName("混合流：user→3分片→2 tool_result→1 response")
  void mixedFlowProducesCorrectMerge() {
    var records =
        List.of(
            user("inspect files"),
            assistantWithMeta("msg-1", null, "I will inspect two files.", List.of()),
            assistantWithMeta(
                "msg-1",
                null,
                "",
                List.of(toolCall("r1", "Read", "{\"file_path\":\"/first.md\"}"))),
            assistantWithMeta(
                "msg-1",
                "tool_use",
                "",
                List.of(toolCall("r2", "Read", "{\"file_path\":\"/second.md\"}"))),
            toolResult("r1"),
            toolResult("r2"),
            assistantWithMeta("msg-2", "end_turn", "Both files inspected.", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(5);
    assertThat(merged.get(0).eventType()).isEqualTo("user");
    assertThat(merged.get(1).eventType()).isEqualTo("assistant");
    assertThat(merged.get(1).responseMessageId()).contains("msg-1");
    assertThat(merged.get(1).content()).isEqualTo("I will inspect two files.");
    assertThat(merged.get(1).toolCalls()).hasSize(2);
    assertThat(merged.get(2).eventType()).isEqualTo("tool_result");
    assertThat(merged.get(3).eventType()).isEqualTo("tool_result");
    assertThat(merged.get(4).eventType()).isEqualTo("assistant");
    assertThat(merged.get(4).responseMessageId()).contains("msg-2");
  }

  @Test
  @DisplayName("usage 取分量最大值，不叠加")
  void usageTakesComponentMax() {
    var first =
        new SourceRecord(
            "loc",
            0,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            new SourceRecordUsage(0, 0, 0, 0),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "text1",
            Optional.of("msg-1"),
            Optional.empty());
    var second =
        new SourceRecord(
            "loc",
            1,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            new SourceRecordUsage(200, 100, 20, 400),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "text2",
            Optional.of("msg-1"),
            Optional.of("end_turn"));

    var merged = QoderResponseRecords.merge(List.of(first, second));

    assertThat(merged).hasSize(1);
    assertThat(merged.get(0).usage().inputTokens()).isEqualTo(200);
    assertThat(merged.get(0).usage().cacheReadInputTokens()).isEqualTo(100);
    assertThat(merged.get(0).usage().cacheCreationInputTokens()).isEqualTo(20);
    assertThat(merged.get(0).usage().outputTokens()).isEqualTo(400);
  }

  @Test
  @DisplayName("不同 scope/subagentId 的同 message.id 不合并")
  void differentScopesDoNotMerge() {
    var mainRelation = SourceRecordRelation.empty();
    var subRelation =
        new SourceRecordRelation(
            Optional.of("sub-agent-1"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());

    var mainRecord =
        new SourceRecord(
            "loc",
            0,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            mainRelation,
            "main text",
            Optional.of("msg-1"),
            Optional.empty());

    var subRecord =
        new SourceRecord(
            "loc",
            1,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            subRelation,
            "sub text",
            Optional.of("msg-1"),
            Optional.empty());

    var merged = QoderResponseRecords.merge(List.of(mainRecord, subRecord));

    assertThat(merged).hasSize(2);
    assertThat(merged.get(0).content()).isEqualTo("main text");
    assertThat(merged.get(1).content()).isEqualTo("sub text");
  }

  @Test
  @DisplayName("合并后 turnId 唯一：同 message.id 跨 stop 边界产生不同 turnId")
  void mergedTurnIdIsUniqueAcrossStopBoundary() {
    var records =
        List.of(
            assistantWithMeta("msg-1", "tool_use", "first", List.of(toolCall("t1", "Read", ""))),
            toolResult("t1"),
            assistantWithMeta("msg-1", "end_turn", "second", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(3);
    // 第一个 assistant 和第二个 assistant 的 turnId 必须不同
    assertThat(merged.get(0).turnId()).isNotEqualTo(merged.get(2).turnId());
  }

  @Test
  @DisplayName("同 parentUuid 但无 message.id 不合并")
  void sameParentUuidWithoutMessageIdDoesNotMerge() {
    // 模拟只有 uuid/parentUuid 没有 message.id 的情况
    var records =
        List.of(
            assistantNoMessageId("uuid-1", "parent-1", "first"),
            assistantNoMessageId("uuid-2", "parent-1", "second"));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(2);
  }

  @Test
  @DisplayName("不同源文件的同 message.id 不合并")
  void differentSourceFilesDoNotMerge() {
    var record1 =
        new SourceRecord(
            "one.jsonl#event[0]",
            0,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "text from one",
            Optional.of("msg-1"),
            Optional.empty());
    var record2 =
        new SourceRecord(
            "two.jsonl#event[0]",
            0,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "text from two",
            Optional.of("msg-1"),
            Optional.empty());

    var merged = QoderResponseRecords.merge(List.of(record1, record2));

    assertThat(merged).hasSize(2);
    assertThat(merged.get(0).content()).isEqualTo("text from one");
    assertThat(merged.get(1).content()).isEqualTo("text from two");
  }

  @Test
  @DisplayName("同 subagentId 但不同 parent relation 不合并")
  void sameSubagentIdDifferentParentRelationDoesNotMerge() {
    var relation1 =
        new SourceRecordRelation(
            Optional.of("sub-1"),
            Optional.of("parent-thread-1"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    var relation2 =
        new SourceRecordRelation(
            Optional.of("sub-1"),
            Optional.of("parent-thread-2"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());

    var record1 =
        new SourceRecord(
            "loc#event[0]",
            0,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            relation1,
            "text1",
            Optional.of("msg-1"),
            Optional.empty());
    var record2 =
        new SourceRecord(
            "loc#event[1]",
            1,
            "assistant",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.of("msg-1"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            relation2,
            "text2",
            Optional.of("msg-1"),
            Optional.empty());

    var merged = QoderResponseRecords.merge(List.of(record1, record2));

    assertThat(merged).hasSize(2);
  }

  @Test
  @DisplayName("生成身份与原始 ID 不碰撞：m1, m1, m1#2 产生 3 个不同 callId")
  void generatedIdsDoNotCollideWithOriginalIds() {
    var records =
        List.of(
            assistantWithMeta("m1", "end_turn", "first", List.of()),
            assistantWithMeta("m1", "end_turn", "second", List.of()),
            assistantWithMeta("m1#2", "end_turn", "third", List.of()));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(3);
    assertThat(merged).extracting(SourceRecord::turnId).doesNotHaveDuplicates();
    assertThat(merged).extracting(SourceRecord::callId).doesNotHaveDuplicates();
    // 所有生成的 ID 都包含 qr$ 前缀
    assertThat(merged)
        .allSatisfy(
            r -> assertThat(r.turnId()).hasValueSatisfying(id -> assertThat(id).startsWith("qr$")));
  }

  @Test
  @DisplayName("无 message.id 的独立响应各自获得唯一身份")
  void noMessageIdRecordsGetUniqueIdentity() {
    var records =
        List.of(
            assistantNoMessageId("uuid-1", "shared-parent", "first"),
            assistantNoMessageId("uuid-2", "shared-parent", "second"));

    var merged = QoderResponseRecords.merge(records);

    assertThat(merged).hasSize(2);
    assertThat(merged.get(0).turnId()).isNotEqualTo(merged.get(1).turnId());
    assertThat(merged.get(0).callId()).isNotEqualTo(merged.get(1).callId());
  }

  private static SourceRecord assistantWithMeta(
      String responseMessageId, String stopReason, String content, List<SourceToolCall> calls) {
    return new SourceRecord(
        "test#event[0]",
        0,
        "assistant",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.ofNullable(responseMessageId),
        SourceRecordUsage.empty(),
        calls,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        content,
        Optional.ofNullable(responseMessageId),
        Optional.ofNullable(stopReason));
  }

  private static SourceRecord assistantNoMessageId(String uuid, String parentUuid, String content) {
    return new SourceRecord(
        "test#event[0]",
        0,
        "assistant",
        Optional.of(uuid),
        Optional.empty(),
        Optional.empty(),
        Optional.of(parentUuid),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        content,
        Optional.empty(),
        Optional.empty());
  }

  private static SourceRecord user(String content) {
    return new SourceRecord(
        "test#event[0]",
        0,
        "user",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        content,
        Optional.empty(),
        Optional.empty());
  }

  private static SourceRecord toolResult(String toolUseId) {
    return new SourceRecord(
        "test#event[0]",
        0,
        "tool_result",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.of(toolUseId),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        "result",
        Optional.empty(),
        Optional.empty());
  }

  private static SourceToolCall toolCall(String id, String name, String input) {
    return new SourceToolCall(id, name, input);
  }
}
