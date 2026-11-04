package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.TitleFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 纯 synthetic 会话验证数字、四段精度及重叠覆盖在持久化/过滤/分组间守恒。 */
class TokenProvenanceQueryTest {
  @TempDir Path tempDir;
  private IndexConnection connection;
  private SqliteSessionQueryRepository sessions;
  private SqliteAggregateQueryRepository aggregates;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("precision.db");
    connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    SqliteIndexWriter writer = new SqliteIndexWriter(connection.writerConnection());
    writer.ensureSchema();
    write(
        writer,
        "estimate",
        NormalizedAgent.QODER,
        "/synthetic/shared",
        20,
        10,
        new TokenProvenance(
            "estimated", "unavailable", "unavailable", "estimated", "visible_context_v1", 1, 1, 0));
    write(
        writer,
        "zero",
        NormalizedAgent.CLAUDE_CODE,
        "/synthetic/shared",
        0,
        0,
        new TokenProvenance(
            "provider_reported",
            "provider_reported",
            "provider_reported",
            "provider_reported",
            "",
            0,
            0,
            0));
    write(
        writer,
        "legacy",
        NormalizedAgent.CODEX,
        "/synthetic/legacy",
        7,
        0,
        TokenProvenance.unknown());
    write(
        writer,
        "mixed",
        NormalizedAgent.QODER,
        "/synthetic/mixed",
        12,
        4,
        new TokenProvenance(
            "mixed", "unavailable", "unavailable", "mixed", "visible_context_v1", 1, 1, 1));
    writer.flushPendingWrites();
    sessions = new SqliteSessionQueryRepository(connection);
    aggregates = new SqliteAggregateQueryRepository(connection);
  }

  @AfterEach
  void close() {
    connection.close();
  }

  @Test
  void cacheKpiExcludesMissingMeasurementsButKeepsReportedZeroRatios() throws Exception {
    var absent = aggregates.kpiSupplement(AgentFilter.NONE);
    assertThat(absent.eligibleSessions()).isZero();
    assertThat(absent.p50CacheRatio()).isNull();
    assertThat(absent.lowReadSessions()).isZero();
    try (var statement = connection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET fresh_input_tokens = 10, total_tokens = 10
          WHERE session_key = 'claude_code:zero'
          """);
      statement.executeUpdate(
          """
          UPDATE sessions SET fresh_input_tokens = 10, cache_read_tokens = 30,
            total_tokens = 40, fresh_input_token_precision = 'provider_reported',
            cache_read_token_precision = 'provider_reported',
            cache_write_token_precision = 'provider_reported'
          WHERE session_key = 'codex:legacy'
          """);
    }
    var measured = aggregates.kpiSupplement(AgentFilter.NONE);
    assertThat(measured.eligibleSessions()).isEqualTo(2);
    assertThat(measured.p50CacheRatio()).isEqualTo(0.375);
    assertThat(measured.lowReadSessions()).isEqualTo(1);
    var missing = aggregates.kpiSupplement(AgentFilter.of("qoder"));
    assertThat(missing.eligibleSessions()).isZero();
    assertThat(missing.p50CacheRatio()).isNull();
    assertThat(missing.lowReadSessions()).isZero();
    var zero = aggregates.kpiSupplement(AgentFilter.of("claude_code"));
    assertThat(zero.eligibleSessions()).isEqualTo(1);
    assertThat(zero.p50CacheRatio()).isZero();
    assertThat(zero.lowReadSessions()).isEqualTo(1);
  }

  @Test
  void reportedZeroIsDistinctFromUnavailableAndLegacyUnknown() {
    SessionRecord zero = sessions.getSession("claude_code:zero").orElseThrow();
    assertThat(zero.totalTokens()).isZero();
    assertThat(zero.tokenProvenance().cacheRead()).isEqualTo("provider_reported");
    assertThat(zero.tokenProvenance().unavailableSessionCount()).isZero();
    SessionRecord estimate = sessions.getSession("qoder:estimate").orElseThrow();
    assertThat(estimate.freshInputTokens()).isEqualTo(20);
    assertThat(estimate.cacheReadTokens()).isZero();
    assertThat(estimate.tokenProvenance().cacheRead()).isEqualTo("unavailable");
    assertThat(estimate.tokenProvenance().estimationMethod()).isEqualTo("visible_context_v1");
    assertThat(sessions.getSession("codex:legacy").orElseThrow().tokenProvenance())
        .isEqualTo(TokenProvenance.unknown());
  }

  @Test
  void mixedAggregationRetainsOverlappingCoverageAcrossEveryConsumer() {
    var summary = sessions.listSummary(SessionListFilter.defaults());
    assertThat(summary.totalTokens()).isEqualTo(53);
    TokenProvenance precision = summary.tokenProvenance();
    assertThat(precision.freshInput()).isEqualTo("mixed");
    assertThat(precision.cacheRead()).isEqualTo("mixed");
    assertThat(precision.estimatedSessionCount()).isEqualTo(2);
    assertThat(precision.unavailableSessionCount()).isEqualTo(2);
    assertThat(precision.unknownSessionCount()).isEqualTo(2);
    assertThat(sessions.listAggregate(SessionListFilter.defaults()).tokenProvenance())
        .isEqualTo(precision);
    assertThat(aggregates.dashboardStats(AgentFilter.NONE).tokenProvenance()).isEqualTo(precision);
    assertThat(aggregates.tokenBreakdown().tokenProvenance()).isEqualTo(precision);
    assertThat(aggregates.projectListSummary(ProjectListFilter.defaults()).tokenProvenance())
        .isEqualTo(precision);
    assertThat(aggregates.trendData(TrendFilter.defaults()))
        .singleElement()
        .satisfies(day -> assertThat(day.tokenProvenance()).isEqualTo(precision));
    var qoder =
        aggregates.agentBreakdown().stream()
            .filter(row -> row.agent().equals("qoder"))
            .findFirst()
            .orElseThrow();
    assertThat(qoder.tokenProvenance().estimatedSessionCount()).isEqualTo(2);
    assertThat(qoder.tokenProvenance().unknownSessionCount()).isEqualTo(1);
    assertThat(aggregates.dashboardStats(AgentFilter.of("qoder")).tokenProvenance())
        .isEqualTo(qoder.tokenProvenance());
    assertThat(
            aggregates.agentEfficiency().stream()
                .filter(row -> row.agent().equals("qoder"))
                .findFirst()
                .orElseThrow()
                .tokenProvenance())
        .isEqualTo(qoder.tokenProvenance());
  }

  @Test
  void provenanceUsesActualFiltersAndProjectGroupsRatherThanUnfilteredTotals() {
    var filter = SessionListFilter.defaults().withTitle(TitleFilter.of("estimate"));
    var summary = sessions.listSummary(filter);
    assertThat(summary.sessionCount()).isEqualTo(1);
    assertThat(summary.tokenProvenance().freshInput()).isEqualTo("estimated");
    assertThat(summary.tokenProvenance().unknownSessionCount()).isZero();
    assertThat(sessions.listSessions(filter).items())
        .singleElement()
        .satisfies(row -> assertThat(row.tokenProvenance()).isEqualTo(summary.tokenProvenance()));
    var shared = aggregates.projectStats("/synthetic/shared");
    assertThat(shared.totalSessions()).isEqualTo(2);
    assertThat(shared.tokenProvenance().freshInput()).isEqualTo("mixed");
    assertThat(shared.tokenProvenance().estimatedSessionCount()).isEqualTo(1);
    assertThat(shared.tokenProvenance().unknownSessionCount()).isZero();
    var projectFilter = ProjectListFilter.defaults().withTitle(TitleFilter.of("shared"));
    assertThat(aggregates.projectListSummary(projectFilter).tokenProvenance())
        .isEqualTo(shared.tokenProvenance());
    assertThat(aggregates.listProjects(projectFilter).items())
        .singleElement()
        .satisfies(row -> assertThat(row.tokenProvenance()).isEqualTo(shared.tokenProvenance()));
    assertThat(
            aggregates.trendData(TrendFilter.defaults().withAgent(AgentFilter.of("claude_code"))))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.tokenProvenance().freshInput()).isEqualTo("provider_reported");
              assertThat(row.totalTokens()).isZero();
            });
    var none = SessionListFilter.defaults().withTitle(TitleFilter.of("not-a-session"));
    assertThat(sessions.listSummary(none).tokenProvenance()).isEqualTo(TokenProvenance.empty());
    assertThat(sessions.listAggregate(none).tokenProvenance()).isEqualTo(TokenProvenance.empty());
  }

  @Test
  void mergingDisjointScopesKeepsEmptyIdentityAndMixedEvidence() {
    TokenProvenance estimate =
        sessions.getSession("qoder:estimate").orElseThrow().tokenProvenance();
    assertThat(TokenProvenance.empty().plus(estimate)).isEqualTo(estimate);
    assertThat(estimate.plus(TokenProvenance.empty())).isEqualTo(estimate);
    TokenProvenance mixed = estimate.plus(TokenProvenance.unknown());
    assertThat(mixed.freshInput()).isEqualTo("mixed");
    assertThat(mixed.estimatedSessionCount()).isEqualTo(1);
    assertThat(mixed.unknownSessionCount()).isEqualTo(1);
  }

  private void write(
      SqliteIndexWriter writer,
      String id,
      NormalizedAgent agent,
      String project,
      long fresh,
      long output,
      TokenProvenance provenance) {
    Map<String, Object> session = new HashMap<>();
    session.put("session_key", agent.getValue() + ":" + id);
    session.put("session_id", id);
    session.put("title", id);
    session.put("project_key", project);
    session.put("project_name", project);
    session.put("model", "synthetic-model");
    String day = LocalDate.now(ZoneOffset.UTC).toString();
    session.put("started_at", day + "T00:00:00Z");
    session.put("ended_at", day + "T12:00:00Z");
    session.put("freshInputTokens", fresh);
    session.put("cacheReadTokens", 0L);
    session.put("cacheWriteTokens", 0L);
    session.put("outputTokens", output);
    session.put("totalTokens", fresh + output);
    session.putAll(provenance.toMetadata());
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            agent,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    writer.writeNormalizedArtifact(
        artifact, tempDir.resolve(id + ".json"), "synthetic.jsonl", 1, 1, Instant.EPOCH);
  }
}
