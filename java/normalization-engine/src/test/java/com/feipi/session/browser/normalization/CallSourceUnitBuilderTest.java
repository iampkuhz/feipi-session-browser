package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class CallSourceUnitBuilderTest {
  @Test
  void consumesOnlyNewInputsInTheSameScopeAndPreservesOrder() {
    var records =
        List.of(
            record("main", "user", " first\n", ""),
            record("child", "user", "child request", ""),
            record("main", "assistant", "answer1", ""),
            record("main", "tool_result", "result A", "A"),
            record("child", "assistant", "child answer", ""),
            record("main", "user", "followup", ""),
            record("main", "tool_result", "result B", "B"),
            record("main", "assistant", "answer2", ""),
            record("main", "user", "future input", ""));
    var calls = CallSourceUnitBuilder.build(records, SourceRecord::locator);
    assertThat(texts(calls.get(0))).containsExactly(" first\n", "answer1");
    assertThat(texts(calls.get(1))).containsExactly("child request", "child answer");
    assertThat(texts(calls.get(2))).containsExactly("result A", "followup", "result B", "answer2");
    assertThat(calls.get(2).get(0)).containsEntry("tool_call_id", "A");
    assertThat(calls.get(2).get(2)).containsEntry("tool_call_id", "B");
  }

  @Test
  void retainsCodexResponseItemsWithoutAddingCallsOrBackfillingFutureInputs() {
    var records =
        List.of(
            record("main", "user", "request", ""),
            record("main", "response_item", "before count", ""),
            record("main", "assistant", "", ""),
            record("main", "response_item", "after count", ""));
    var calls = CallSourceUnitBuilder.build(records, SourceRecord::locator);
    assertThat(calls).hasSize(1);
    assertThat(texts(calls.get(0))).containsExactly("request", "before count", "", "after count");
    var withFutureInput = new java.util.ArrayList<>(records);
    withFutureInput.add(3, record("main", "user", "", ""));
    var guarded = CallSourceUnitBuilder.build(withFutureInput, SourceRecord::locator);
    assertThat(texts(guarded.get(0))).containsExactly("request", "before count", "");
  }

  @Test
  void codexResponseStaysBeforeTheNextInputBoundary() {
    var records =
        List.of(
            record("main", "user", "U1", ""),
            record("main", "assistant", "", ""),
            record("main", "response_item", "A1", ""),
            record("main", "user", "U2", ""),
            record("main", "assistant", "", ""),
            record("main", "response_item", "A2", ""));
    var calls = CallSourceUnitBuilder.build(records, SourceRecord::locator);
    assertThat(texts(calls.get(0))).containsExactly("U1", "", "A1");
    assertThat(texts(calls.get(1))).containsExactly("U2", "", "A2");
    var unfinished = CallSourceUnitBuilder.build(records.subList(0, 4), SourceRecord::locator);
    assertThat(texts(unfinished.get(0))).containsExactly("U1", "", "A1");
  }

  private static List<Object> texts(List<Map<String, Object>> units) {
    return units.stream().map(unit -> unit.get("text")).toList();
  }

  private static SourceRecord record(String scope, String type, String text, String toolId) {
    return new SourceRecord(
        scope,
        0,
        type,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        toolId.isEmpty() ? Optional.empty() : Optional.of(toolId),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        text);
  }
}
