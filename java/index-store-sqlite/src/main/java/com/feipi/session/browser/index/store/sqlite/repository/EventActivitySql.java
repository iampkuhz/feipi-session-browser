package com.feipi.session.browser.index.store.sqlite.repository;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 将经过严格校验的事件摘要转换成现有事务队列中的标量 SQL。 */
final class EventActivitySql {
  static final List<String> TABLES =
      List.of("event_activity_tokens", "event_activity_days", "event_activity_coverage");
  static final List<String> COVERAGE =
      List.of(
          "observedUserMessages",
          "undatedUserMessages",
          "supportedUsageEvents",
          "undatedUsageEvents",
          "unsupportedUsageEvents");
  static final List<String> COMPONENTS = List.of("fresh", "cacheRead", "cacheWrite", "output");
  static final List<String> FIELDS =
      List.of(
          "reportedTokens",
          "reportedSamples",
          "estimatedSamples",
          "unavailableSamples",
          "unknownSamples",
          "mixedSamples");

  private EventActivitySql() {}

  static String quote(String text) {
    return "'" + text.replace("'", "''") + "'";
  }

  static List<String> replacement(String key, Object value) {
    List<String> sql = new ArrayList<>();
    for (String table : TABLES)
      sql.add("DELETE FROM " + table + " WHERE session_key = " + quote(key));
    if (value == null) return sql;
    Map<?, ?> summary = map(value);
    if (integer(summary.get("version")) != 1
        || !"source_event_utc".equals(summary.get("basis"))
        || !"codex_modern_usage_report_day".equals(summary.get("tokenBasis"))) {
      throw new IllegalArgumentException("Unsupported event activity metadata");
    }
    List<String> counts = new ArrayList<>();
    for (String field : COVERAGE) counts.add(Long.toString(integer(summary.get(field))));
    sql.add(
        "INSERT INTO event_activity_coverage VALUES ("
            + quote(key)
            + ","
            + String.join(",", counts)
            + ")");
    Map<?, ?> days = map(summary.get("days"));
    for (var entry : days.entrySet()) {
      LocalDate date = LocalDate.parse(text(entry.getKey()));
      Map<?, ?> day = map(entry.getValue());
      Instant latest = Instant.parse(text(day.get("latestEventTimestamp")));
      if (!latest.atOffset(ZoneOffset.UTC).toLocalDate().equals(date))
        throw new IllegalArgumentException("Event timestamp does not match UTC day");
      long messages = integer(day.get("observedUserMessages"));
      sql.add(
          "INSERT INTO event_activity_days VALUES ("
              + quote(key)
              + ","
              + date.toEpochDay()
              + ","
              + quote(latest.toString())
              + ","
              + messages
              + ")");
      tokens(sql, key, Long.toString(date.toEpochDay()), day.get("tokens"));
    }
    tokens(sql, key, "undated", summary.get("undatedTokens"));
    return sql;
  }

  private static void tokens(List<String> sql, String key, String day, Object value) {
    Map<?, ?> components = map(value);
    if (!components.keySet().equals(Set.copyOf(COMPONENTS)))
      throw new IllegalArgumentException("Four event token components required");
    for (String component : COMPONENTS) {
      Map<?, ?> fields = map(components.get(component));
      List<String> values = new ArrayList<>();
      for (String field : FIELDS) values.add(Long.toString(integer(fields.get(field))));
      if (integer(fields.get("reportedSamples")) == 0 && integer(fields.get("reportedTokens")) != 0)
        throw new IllegalArgumentException("Unreported token amount must be zero");
      sql.add(
          "INSERT INTO event_activity_tokens VALUES ("
              + quote(key)
              + ","
              + quote(day)
              + ","
              + quote(component)
              + ","
              + String.join(",", values)
              + ")");
    }
  }

  private static Map<?, ?> map(Object value) {
    if (value instanceof Map<?, ?> result) return result;
    throw new IllegalArgumentException("Event activity object required");
  }

  private static String text(Object value) {
    if (value instanceof String result) return result;
    throw new IllegalArgumentException("Event activity text required");
  }

  private static long integer(Object value) {
    if ((value instanceof Byte
            || value instanceof Short
            || value instanceof Integer
            || value instanceof Long)
        && ((Number) value).longValue() >= 0) return ((Number) value).longValue();
    throw new IllegalArgumentException("Nonnegative event activity integer required");
  }
}
