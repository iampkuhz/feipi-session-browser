package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceTiming;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 显式消息角色与默认未知角色在复制、混合块和 meta 中保持原义。 */
class MessageRoleEvidenceTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  void explicitMessagesHaveRolesButToolResultsDoNot() throws Exception {
    var assistant =
        JsonSourceRecordMapper.toSourceRecords(
                "synthetic",
                0,
                MAPPER.readTree("{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\"}}"),
                "assistant")
            .getFirst();
    assertThat(assistant.messageRole()).contains("assistant");
    var blocks =
        JsonSourceRecordMapper.toSourceRecords(
            "synthetic",
            1,
            MAPPER.readTree(
                """
        {"type":"user","message":{"content":[
          {"type":"tool_result","tool_use_id":"tool","content":"result"},
          {"type":"text","text":"prompt"}]}}
        """),
            "user");
    assertThat(blocks).hasSize(2);
    assertThat(blocks.getFirst().messageRole()).isEmpty();
    assertThat(blocks.getLast().messageRole()).contains("user");
  }

  @Test
  void explicitTopLevelRoleCanIdentifyWrappedMessages() throws Exception {
    var record =
        JsonSourceRecordMapper.toSourceRecords(
                "synthetic",
                0,
                MAPPER.readTree(
                    "{\"type\":\"message\",\"role\":\"assistant\",\"content\":\"answer\"}"),
                "assistant")
            .getFirst();
    assertThat(record.messageRole()).contains("assistant");
  }

  @Test
  void unknownRoleIsDefaultAndCopiesPreserveExplicitEvidence() {
    var legacy = SourceRecord.of("synthetic#event[0]", 0, "assistant");
    assertThat(legacy.messageRole()).isEmpty();
    var explicit = legacy.withMessageRole(Optional.of("assistant"));
    assertThat(explicit.withContent("answer").withTiming(SourceTiming.empty()).messageRole())
        .contains("assistant");
    assertThatThrownBy(() -> legacy.withMessageRole(Optional.of("guessed")))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void metaRemainsContextEvenWhenSourceExplicitlyHasUserRole() throws Exception {
    var meta =
        JsonSourceRecordMapper.toSourceRecords(
                "synthetic",
                0,
                MAPPER.readTree("{\"type\":\"user\",\"isMeta\":true,\"content\":\"context\"}"),
                "user")
            .getFirst();
    assertThat(meta.metaContext()).isTrue();
    assertThat(meta.messageRole()).contains("user");
  }
}
