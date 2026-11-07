package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import org.junit.jupiter.api.Test;

class SessionsApiHandlerTest {
  @Test
  void listDtoSeparatesLogicalRoundsCallsAndAssistantMessages() {
    var dto = SessionsApiHandler.rowDto(row(1L, 2L, true, 7, true, 1L));
    assertThat(dto.rounds()).isEqualTo(1L);
    assertThat(dto.llmCalls()).isEqualTo(2L);
    assertThat(dto.modelCallCount()).isEqualTo(1L);
    assertThat(dto.assistantMessages()).isEqualTo(7L);
    assertThat(dto.tools()).isZero();
    assertThat(dto.subagents()).isZero();
    assertThat(dto.failedTools()).isZero();
  }

  @Test
  void missingContentDoesNotMasqueradeAsObservedZeros() {
    var dto = SessionsApiHandler.rowDto(row(null, null, false));
    assertThat(dto.rounds()).isNull();
    assertThat(dto.llmCalls()).isNull();
    assertThat(dto.modelCallCount()).isNull();
    assertThat(dto.assistantMessages()).isNull();
    assertThat(dto.tools()).isNull();
    assertThat(dto.subagents()).isNull();
    assertThat(dto.failedTools()).isNull();
  }

  @Test
  void contentWithoutExplicitAssistantRoleIsNotAMeasuredMessageCount() {
    var dto = SessionsApiHandler.rowDto(row(1L, 2L, true, 0, false, null));
    assertThat(dto.rounds()).isEqualTo(1L);
    assertThat(dto.assistantMessages()).isNull();
  }

  @Test
  void explicitlyMeasuredZeroAssistantMessagesRemainsZero() {
    var dto = SessionsApiHandler.rowDto(row(1L, 2L, true, 0, true, 0L));
    assertThat(dto.assistantMessages()).isZero();
    assertThat(dto.modelCallCount()).isZero();
  }

  private static SessionRow row(Long rounds, Long calls, boolean measured) {
    return row(rounds, calls, measured, 7, measured, null);
  }

  private static SessionRow row(
      Long rounds,
      Long calls,
      boolean measured,
      long assistantCount,
      boolean roleMeasured,
      Long modelCalls) {
    return new SessionRow(
        "codex:metrics",
        "codex",
        "metrics",
        "Fixture",
        "",
        "",
        "",
        "",
        "",
        0,
        0,
        0,
        "",
        "",
        "",
        1,
        assistantCount,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        "fixture",
        TokenProvenance.unknown(1),
        SessionTiming.unknown(null),
        rounds,
        calls,
        measured,
        roleMeasured,
        roleMeasured,
        modelCalls);
  }
}
