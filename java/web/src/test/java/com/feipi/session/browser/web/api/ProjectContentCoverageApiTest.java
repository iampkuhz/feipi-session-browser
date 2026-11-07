package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import com.feipi.session.browser.web.WebTestComposition;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 独立覆盖项目列表、详情和 agent 工具失败计数的内容测量样本，不更改分页 fixture。 */
class ProjectContentCoverageApiTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  @TempDir Path directory;

  @Test
  void projectApisDiscloseUnknownMeasuredZeroAndMixedContentWithoutInventingTokenCoverage()
      throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("project-api-coverage.db");
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
      var root =
          new WebCompositionRoot(
              WebTestComposition.queryRoot(connection, new SchemaVersion(1)), WebConfig.defaults());
      JavalinTest.test(
          root.app(),
          (app, client) -> {
            for (String shape : new String[] {"unknown", "zero", "mixed"}) {
              long samples = "unknown".equals(shape) ? 0 : 1;
              long total = "mixed".equals(shape) ? 2 : 1;
              long tools = "mixed".equals(shape) ? 4 : 0;
              long failed = "mixed".equals(shape) ? 1 : 0;
              var summaryResponse = client.get("/api/projects/summary?q=coverage-" + shape);
              assertThat(summaryResponse.code()).isEqualTo(200);
              JsonNode summary = MAPPER.readTree(summaryResponse.body().string());
              assertThat(summary.has("contentSampleCount")).isTrue();
              assertThat(summary.at("/contentSampleCount").asLong()).isEqualTo(samples);
              assertThat(summary.at("/sessionCount").asLong()).isEqualTo(total);
              assertThat(summary.at("/toolCalls").asLong()).isEqualTo(tools);
              assertThat(summary.at("/failedTools").asLong()).isEqualTo(failed);
              var rowsResponse = client.get("/api/projects/rows?q=coverage-" + shape);
              assertThat(rowsResponse.code()).isEqualTo(200);
              JsonNode rows = MAPPER.readTree(rowsResponse.body().string());
              assertThat(rows.at("/rows/0/contentSampleCount").asLong()).isEqualTo(samples);
              assertThat(rows.at("/rows/0/totalSessions").asLong()).isEqualTo(total);
              var detailResponse = client.get("/api/projects/coverage-" + shape + "/summary");
              assertThat(detailResponse.code()).isEqualTo(200);
              JsonNode detail = MAPPER.readTree(detailResponse.body().string());
              assertThat(detail.has("contentSampleCount")).isTrue();
              assertThat(detail.at("/contentSampleCount").asLong()).isEqualTo(samples);
              assertThat(detail.at("/toolCalls").asLong()).isEqualTo(tools);
              assertThat(detail.at("/failedTools").asLong()).isEqualTo(failed);
              assertThat(detail.at("/tokens/provenance/freshInput").asText()).isEqualTo("unknown");
              var mixResponse = client.get("/api/projects/coverage-" + shape + "/agent-mix");
              assertThat(mixResponse.code()).isEqualTo(200);
              JsonNode mix = MAPPER.readTree(mixResponse.body().string());
              JsonNode codex = null;
              for (JsonNode row : mix.at("/rows"))
                if ("codex".equals(row.at("/agent").asText())) codex = row;
              assertThat(codex).isNotNull();
              assertThat(codex.at("/contentSampleCount").asLong()).isEqualTo(samples);
              assertThat(codex.at("/failedTools").asLong()).isEqualTo(failed);
            }
          });
    }
  }
}
