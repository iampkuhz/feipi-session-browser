package com.feipi.session.browser.index.api.query;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** 事件观察结果保留未知、实测零和不可变快照。 */
class EventActivityTest {
  @Test
  void measuredZeroIsNotAnUnknownAmount() {
    var measured = new EventActivity.TokenComponent(0L, 1, 0, 0, 0, 0);
    var unknown = new EventActivity.TokenComponent(null, 0, 0, 0, 1, 0);
    assertThat(measured.reportedTokens()).isZero();
    assertThat(unknown.reportedTokens()).isNull();
    assertThatThrownBy(() -> new EventActivity.TokenComponent(0L, 0, 0, 0, 0, 0))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new EventActivity.TokenComponent(null, 1, 0, 0, 0, 0))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new EventActivity.TokenComponent(-1L, 1, 0, 0, 0, 0))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new EventActivity.TokenComponent(null, 0, -1, 0, 0, 0))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void resultDefensivelyCopiesEveryMutableContainer() {
    var empty = new EventActivity.TokenComponent(null, 0, 0, 0, 0, 0);
    var tokens = new LinkedHashMap<String, EventActivity.TokenComponent>();
    for (String component : new String[] {"fresh", "cacheRead", "cacheWrite", "output"}) {
      tokens.put(component, empty);
    }
    var day = new EventActivity.Day("2026-04-02", 2, tokens);
    var days = new ArrayList<EventActivity.Day>();
    days.add(day);
    var coverage = new LinkedHashMap<>(Map.of("indexedSessions", 3L, "unknownSessions", 2L));
    var result = new EventActivity(days, coverage, tokens);
    days.clear();
    coverage.clear();
    tokens.clear();
    assertThat(result.days()).containsExactly(day);
    assertThat(result.coverage()).containsEntry("unknownSessions", 2L);
    assertThat(day.tokens()).hasSize(4);
    assertThat(result.undatedTokens()).hasSize(4);
    assertThatThrownBy(() -> result.days().clear())
        .isInstanceOf(UnsupportedOperationException.class);
    assertThatThrownBy(() -> day.tokens().clear())
        .isInstanceOf(UnsupportedOperationException.class);
    assertThatThrownBy(() -> new EventActivity.Day("not-a-date", 1, result.undatedTokens()))
        .isInstanceOf(java.time.format.DateTimeParseException.class);
    assertThatThrownBy(() -> new EventActivity.Day("2026-04-02", -1, result.undatedTokens()))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new EventActivity.Day("2026-04-02", 1, Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
