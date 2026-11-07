package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.TitleFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成项目验证内容测量覆盖与原始工具计数独立，不从零值或 token 推断覆盖。 */
class ProjectContentCoverageQueryTest {
  @TempDir Path directory;

  @Test
  void unknownSessionTimeDoesNotEraseKnownProjectFirstSeen() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("project-times.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key,session_id,agent,project_key,started_at,ended_at)
            VALUES ('unknown','unknown','codex','mixed','',''),
              ('known','known','codex','mixed','2026-01-02T00:00:00Z','2026-01-03T00:00:00Z'),
              ('empty','empty','codex','only-unknown','','')
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var mixed = repository.projectStats("mixed");
      assertThat(mixed.firstSeen()).isEqualTo("2026-01-02T00:00:00Z");
      assertThat(mixed.lastSeen()).isEqualTo("2026-01-03T00:00:00Z");
      assertThat(repository.projectStats("only-unknown").firstSeen()).isEmpty();
      assertThat(repository.listProjects(ProjectListFilter.defaults()).items())
          .filteredOn(project -> project.projectKey().equals("mixed"))
          .singleElement()
          .satisfies(project -> assertThat(project.firstSeen()).isEqualTo(mixed.firstSeen()));
    }
  }

  @Test
  void projectRowsAndFilteredSummaryPreserveUnknownMeasuredZeroAndMixedCoverage() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("project-coverage.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
      try (var statement = connection.writerConnection().createStatement()) {
        statement.executeUpdate(
            """
            INSERT INTO sessions(session_key,session_id,agent,project_key,project_name,ended_at,
              content_measured,tool_call_count,failed_tool_count)
            VALUES ('u','u','codex','coverage-unknown','coverage-unknown','2026-01-01',0,0,0),
              ('z','z','codex','coverage-zero','coverage-zero','2026-01-01',1,0,0),
              ('m-u','m-u','codex','coverage-mixed','coverage-mixed','2026-01-01',0,0,0),
              ('m-k','m-k','codex','coverage-mixed','coverage-mixed','2026-01-01',1,4,1)
            """);
      }
      var repository = new SqliteAggregateQueryRepository(connection);
      var unknown = repository.projectStats("coverage-unknown");
      assertThat(unknown.contentSampleCount()).isZero();
      assertThat(unknown.totalToolCalls()).isZero();
      var zero = repository.projectStats("coverage-zero");
      assertThat(zero.contentSampleCount()).isEqualTo(1);
      assertThat(zero.totalToolCalls()).isZero();
      var mixed = repository.projectStats("coverage-mixed");
      assertThat(mixed.totalSessions()).isEqualTo(2);
      assertThat(mixed.contentSampleCount()).isEqualTo(1);
      assertThat(mixed.totalToolCalls()).isEqualTo(4);
      assertThat(mixed.totalFailedTools()).isEqualTo(1);
      var filtered = ProjectListFilter.defaults().withTitle(TitleFilter.of("coverage-mixed"));
      assertThat(repository.listProjects(filtered).items())
          .singleElement()
          .satisfies(
              row -> {
                assertThat(row.contentSampleCount()).isEqualTo(1);
                assertThat(row.totalSessions()).isEqualTo(2);
              });
      var summary = repository.projectListSummary(filtered);
      assertThat(summary.contentSampleCount()).isEqualTo(1);
      assertThat(summary.sessionCount()).isEqualTo(2);
      assertThat(summary.toolCallCount()).isEqualTo(4);
      assertThat(repository.projectListSummary(ProjectListFilter.defaults()).contentSampleCount())
          .isEqualTo(2);
    }
  }
}
