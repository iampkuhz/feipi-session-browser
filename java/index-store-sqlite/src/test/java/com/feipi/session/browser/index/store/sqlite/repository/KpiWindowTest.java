package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** UTC 窗口使用 SQLite 同一时钟；所有数据仅为 synthetic。 */
class KpiWindowTest {
  @TempDir Path directory;

  @Test
  void promptCohortsExposeMeasuredSumsAndIndependentSampleWeights() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("prompt-samples.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key,session_id,agent,project_key,started_at,ended_at,
              user_message_count,user_message_measured)
            VALUES ('usage','usage','codex','p',date('now','-2 days'),date('now'),1000,0),
              ('zero','zero','codex','p',date('now','-2 days'),date('now'),0,1),
              ('six','six','codex','p',date('now','-2 days'),date('now'),6,1),
              ('nine','nine','codex','p',date('now','-1 day'),date('now'),9,1),
              ('other','other','qoder','p',date('now','-1 day'),date('now'),4,1)
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var rows = repository.activityTrend(TrendFilter.ofDays(7));
      assertThat(rows).hasSize(2);
      assertThat(rows.getFirst().totalPrompts()).isEqualTo(1006);
      assertThat(rows.getFirst().measuredUserMessages()).isEqualTo(6);
      assertThat(rows.getFirst().userMessageSampleCount()).isEqualTo(2);
      assertThat(rows.getFirst().codexMeasuredUserMessages()).isEqualTo(6);
      assertThat(rows.getFirst().codexUserMessageSampleCount()).isEqualTo(2);
      assertThat(rows.getLast().measuredUserMessages()).isEqualTo(13);
      assertThat(rows.getLast().userMessageSampleCount()).isEqualTo(2);
      assertThat(rows.getLast().qoderMeasuredUserMessages()).isEqualTo(4);
      assertThat(rows.getLast().qoderUserMessageSampleCount()).isEqualTo(1);
      var scoped =
          repository.activityTrend(TrendFilter.ofDays(7).withAgent(AgentFilter.of("codex")));
      assertThat(scoped.getLast().measuredUserMessages()).isEqualTo(9);
      assertThat(scoped.getLast().userMessageSampleCount()).isEqualTo(1);
      assertThat(scoped.getLast().qoderUserMessageSampleCount()).isZero();
    }
  }

  @Test
  void messageMeansUseIndependentMeasuredFlagsAndKeepObservedZero() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("message-coverage.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key,session_id,agent,project_key,ended_at,content_measured,
              user_message_count,assistant_message_count,user_message_measured,assistant_message_measured)
            VALUES ('usage-only','usage-only','codex','p','2026-01-01',1,1000,1000,0,0),
              ('zero','zero','codex','p','2026-01-01',1,0,0,1,1),
              ('user-only','user-only','codex','p','2026-01-01',1,6,100,1,0),
              ('assistant-only','assistant-only','codex','p','2026-01-01',1,100,8,0,1),
              ('other','other','qoder','p','2026-01-01',1,10,12,1,1)
            """);
        statement.executeUpdate(
            """
            INSERT INTO session_artifacts(session_key,artifact_type,path)
            SELECT session_key,'normalized','synthetic-message-coverage' FROM sessions
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var codex = repository.kpiSupplement(AgentFilter.of("codex"));
      assertThat(codex.contentSampleCount()).isEqualTo(4);
      assertThat(codex.userMessageSampleCount()).isEqualTo(2);
      assertThat(codex.assistantMessageSampleCount()).isEqualTo(2);
      assertThat(codex.avgUserMessagesPerSession()).isEqualTo(3);
      assertThat(codex.avgAssistantMessagesPerSession()).isEqualTo(4);
      var all = repository.kpiSupplement(AgentFilter.NONE);
      assertThat(all.userMessageSampleCount()).isEqualTo(3);
      assertThat(all.assistantMessageSampleCount()).isEqualTo(3);
      assertThat(all.avgUserMessagesPerSession()).isEqualTo(16 / 3.0);
      assertThat(all.avgAssistantMessagesPerSession()).isEqualTo(20 / 3.0);
      var absent = repository.kpiSupplement(AgentFilter.of("claude_code"));
      assertThat(absent.userMessageSampleCount()).isZero();
      assertThat(absent.assistantMessageSampleCount()).isZero();
      assertThat(absent.avgUserMessagesPerSession()).isNull();
      assertThat(absent.avgAssistantMessagesPerSession()).isNull();
    }
  }

  @Test
  void cohortQueriesExcludeFutureInstantsBeforeDailyAggregationAcrossScopes() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("future-cohort.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key, session_id, agent, project_key, started_at, ended_at,
              user_message_count, tool_call_count)
            VALUES
              ('known','known','codex','p',datetime('now','-1 minute'),datetime('now','-1 minute'),2,3),
              ('other','other','qoder','p',datetime('now','-1 minute'),datetime('now','-1 minute'),4,5),
              ('same-day-future','same-day-future','codex','p',
                strftime('%Y-%m-%dT23:59:59.999Z','now'),datetime('now','+1 day'),100,100),
              ('next-day-future','next-day-future','qoder','p',
                datetime('now','+1 day'),datetime('now','+1 day'),100,100)
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var all = TrendFilter.ofDays(2);
      var codex = all.withAgent(AgentFilter.of("codex"));
      assertThat(repository.trendData(all).stream().mapToLong(row -> row.totalCount()).sum())
          .isEqualTo(2);
      assertThat(repository.trendData(codex).stream().mapToLong(row -> row.totalCount()).sum())
          .isEqualTo(1);
      assertThat(repository.activityTrend(all).stream().mapToLong(row -> row.totalPrompts()).sum())
          .isEqualTo(6);
      assertThat(
              repository.activityTrend(codex).stream().mapToLong(row -> row.totalPrompts()).sum())
          .isEqualTo(2);
      assertThat(repository.activityTrend(codex).stream().mapToLong(row -> row.toolCalls()).sum())
          .isEqualTo(3);
    }
  }

  @Test
  void windowsExcludeFutureUseFirstSeenAndCountSevenStartDates() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("windows.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key, session_id, agent, project_key, started_at, ended_at)
            VALUES
              ('old', 'old', 'codex', 'existing', datetime('now','-20 days'), datetime('now','-20 days')),
              ('recent', 'recent', 'codex', 'existing', datetime('now','-1 hour'), datetime('now','-1 hour')),
              ('new', 'new', 'codex', 'new', datetime('now','-2 hours'), datetime('now','-2 hours')),
              ('future', 'future', 'codex', 'future', datetime('now','+2 days'), datetime('now','+2 days')),
              ('outside', 'outside', 'codex', 'outside', datetime('now','-30 hours'), datetime('now','-30 hours')),
              ('eighth', 'eighth', 'codex', 'eighth', date('now','-7 days'), date('now','-7 days')),
              ('other', 'other', 'qoder', 'other', datetime('now','-1 hour'), datetime('now','-1 hour'))
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var scoped = repository.kpiSupplement(AgentFilter.of("codex"));
      assertThat(scoped.activeProjects24h()).isEqualTo(2);
      assertThat(scoped.newProjects7d()).isEqualTo(2);
      assertThat(scoped.avgDailySessions7d()).isEqualTo(3 / 7.0);
      assertThat(repository.kpiSupplement(AgentFilter.NONE).activeProjects24h()).isEqualTo(3);
    }
  }

  @Test
  void unknownSamplesAreExcludedAndObservedZeroRemainsEligible() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("coverage.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key,session_id,agent,project_key,model,started_at,ended_at,
              duration_seconds,total_tokens,tool_call_count,failed_tool_count,
              assistant_message_count,content_measured,assistant_message_measured)
            VALUES ('unknown','unknown','codex','p','m','2026-01-01','2026-01-01',0,0,0,0,0,0,0),
              ('zero','zero','codex','p','m','2026-01-01','2026-01-01',0,0,0,0,0,1,1),
              ('measured','measured','codex','p','m','2026-01-01','2026-01-02',20,100,4,2,6,1,1)
            """);
        statement.executeUpdate(
            """
            INSERT INTO session_artifacts(session_key,artifact_type,path)
            VALUES ('unknown','normalized','synthetic-metadata'),
              ('zero','normalized','synthetic'), ('measured','normalized','synthetic')
            """);
        statement.executeUpdate(
            """
            UPDATE sessions SET fresh_input_token_precision='provider_reported',
              cache_read_token_precision='provider_reported',
              cache_write_token_precision='provider_reported', output_token_precision='provider_reported'
            WHERE session_key != 'unknown'
            """);
        statement.executeUpdate(
            "UPDATE sessions SET fresh_input_tokens=100 WHERE session_key='measured'");
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var kpi = repository.kpiSupplement(AgentFilter.NONE);
      assertThat(kpi.contentSampleCount()).isEqualTo(2);
      assertThat(kpi.durationSampleCount()).isEqualTo(2);
      assertThat(kpi.tokenSampleCount()).isEqualTo(2);
      assertThat(kpi.medianDurationSeconds()).isEqualTo(10);
      // 消息均值使用独立消息测量，不从 content coverage 推断。
      assertThat(kpi.assistantMessageSampleCount()).isEqualTo(2);
      assertThat(kpi.avgAssistantMessagesPerSession()).isEqualTo(3);
      assertThat(repository.agentEfficiency())
          .singleElement()
          .satisfies(
              row -> {
                assertThat(row.sessionCount()).isEqualTo(3);
                assertThat(row.durationSampleCount()).isEqualTo(2);
                assertThat(row.tokenSampleCount()).isEqualTo(2);
                assertThat(row.contentSampleCount()).isEqualTo(2);
                assertThat(row.avgDuration()).isEqualTo(10);
                assertThat(row.avgTotalTokens()).isEqualTo(50);
                assertThat(row.avgTools()).isEqualTo(2);
                assertThat(row.failedPerSession()).isEqualTo(1);
                assertThat(row.toolsPerRound()).isNull();
              });
    }
  }
}
