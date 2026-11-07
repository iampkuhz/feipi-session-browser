package com.feipi.session.browser.index.store.sqlite.repository;

import com.feipi.session.browser.index.api.query.EventActivity;
import com.feipi.session.browser.query.api.TrendFilter;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

/** 仅从同一索引快照读取事件标量；未来混桶暂排，结果是观察下界。 */
final class EventActivityQuery {
  private EventActivityQuery() {}

  static EventActivity read(Connection connection, TrendFilter filter) throws SQLException {
    Instant asOf = Instant.now();
    long firstDay =
        asOf.atOffset(ZoneOffset.UTC).toLocalDate().minusDays(filter.days() - 1L).toEpochDay();
    String selected = "SELECT session_key FROM sessions WHERE (? = '' OR agent = ?)";
    Map<String, Long> coverage = new LinkedHashMap<>();
    for (String name :
        new String[] {
          "indexedSessions",
          "summarizedSessions",
          "unknownSessions",
          "futureExcludedDayBuckets",
          "futureExcludedObservedUserMessages"
        }) coverage.put(name, 0L);
    for (String name : EventActivitySql.COVERAGE) coverage.put(name, 0L);
    try (var statement =
        connection.prepareStatement(
            "SELECT c.* FROM sessions s LEFT JOIN event_activity_coverage c ON c.session_key ="
                + " s.session_key WHERE (? = '' OR s.agent = ?)")) {
      bind(statement, filter);
      try (var rows = statement.executeQuery()) {
        while (rows.next()) {
          add(coverage, "indexedSessions", 1);
          if (rows.getString("session_key") == null) add(coverage, "unknownSessions", 1);
          else {
            add(coverage, "summarizedSessions", 1);
            for (String name : EventActivitySql.COVERAGE) add(coverage, name, rows.getLong(name));
          }
        }
      }
    }
    Map<Long, Bucket> days = new TreeMap<>();
    try (var statement =
        connection.prepareStatement(
            "SELECT d.* FROM event_activity_days d WHERE session_key IN (" + selected + ")")) {
      bind(statement, filter);
      try (var rows = statement.executeQuery()) {
        while (rows.next()) {
          long day = rows.getLong("epoch_day");
          long messages = rows.getLong("observed_user_messages");
          if (Instant.parse(rows.getString("latest_event_timestamp")).isAfter(asOf)) {
            add(coverage, "futureExcludedDayBuckets", 1);
            add(coverage, "futureExcludedObservedUserMessages", messages);
          } else if (day >= firstDay) {
            var bucket = days.computeIfAbsent(day, ignored -> new Bucket());
            bucket.messages = Math.addExact(bucket.messages, messages);
          }
        }
      }
    }
    Bucket undated = new Bucket();
    try (var statement =
        connection.prepareStatement(
            "SELECT t.*, d.latest_event_timestamp FROM event_activity_tokens t LEFT JOIN"
                + " event_activity_days d ON d.session_key = t.session_key AND CAST(d.epoch_day AS"
                + " TEXT) = t.day_key WHERE t.session_key IN ("
                + selected
                + ")")) {
      bind(statement, filter);
      try (var rows = statement.executeQuery()) {
        while (rows.next()) {
          String day = rows.getString("day_key");
          if ("undated".equals(day)) undated.accept(rows);
          else {
            long epochDay = Long.parseLong(day);
            if (epochDay >= firstDay
                && !Instant.parse(rows.getString("latest_event_timestamp")).isAfter(asOf)) {
              var bucket = days.get(epochDay);
              if (bucket != null) bucket.accept(rows);
            }
          }
        }
      }
    }
    var result = new ArrayList<EventActivity.Day>();
    days.forEach(
        (date, bucket) ->
            result.add(
                new EventActivity.Day(
                    LocalDate.ofEpochDay(date).toString(), bucket.messages, bucket.tokens())));
    return new EventActivity(result, coverage, undated.tokens());
  }

  private static void bind(java.sql.PreparedStatement statement, TrendFilter filter)
      throws SQLException {
    statement.setString(1, filter.agentFilter().agent());
    statement.setString(2, filter.agentFilter().agent());
  }

  private static void add(Map<String, Long> values, String key, long amount) {
    values.put(key, Math.addExact(values.get(key), amount));
  }

  /** 单个已发生日或未日期化分量的标量合计，不保留源记录或正文。 */
  private static final class Bucket {
    private long messages;
    private final Map<String, long[]> components = new LinkedHashMap<>();

    private Bucket() {
      for (String name : EventActivitySql.COMPONENTS) components.put(name, new long[6]);
    }

    private void accept(ResultSet row) throws SQLException {
      long[] values = components.get(row.getString("component"));
      for (int i = 0; i < values.length; i++)
        values[i] = Math.addExact(values[i], row.getLong(EventActivitySql.FIELDS.get(i)));
    }

    private Map<String, EventActivity.TokenComponent> tokens() {
      Map<String, EventActivity.TokenComponent> result = new LinkedHashMap<>();
      components.forEach(
          (name, values) ->
              result.put(
                  name,
                  new EventActivity.TokenComponent(
                      values[1] == 0 ? null : Long.valueOf(values[0]),
                      values[1],
                      values[2],
                      values[3],
                      values[4],
                      values[5])));
      return result;
    }
  }
}
