package com.feipi.session.browser.contracttest.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.query.ActivityTrend;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.scan.artifact.NormalizedArtifactWriter;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Codex Prompt 趋势集成测试。
 *
 * <p>验证完整链路：raw JSONL -> CodexSourceAdapter -> NormalizationEngine -> SQLite writer ->
 * activityTrend 查询。
 */
@DisplayName("Codex Prompt 趋势集成测试")
class CodexPromptTrendIntegrationTest {

  @TempDir Path tempDir;

  private Connection connection;
  private Path dbFile;
  private SqliteIndexWriter indexWriter;
  private SqliteAggregateQueryRepository queryRepository;
  private CodexSourceAdapter adapter;
  private NormalizationEngine normalizationEngine;

  @BeforeEach
  void setUp() throws Exception {
    dbFile = tempDir.resolve("test.db");
    connection = java.sql.DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
    SqliteTestHelper.configureConnection(connection);
    indexWriter = new SqliteIndexWriter(connection);
    indexWriter.ensureSchema();
    queryRepository =
        new SqliteAggregateQueryRepository(
            IndexConnection.withDefaults(connection, "jdbc:sqlite:" + dbFile.toAbsolutePath()));
    adapter = new CodexSourceAdapter();
    normalizationEngine = new NormalizationEngine();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(connection);
  }

  @Test
  @DisplayName("两日 Codex 消息准确计数")
  void twoDayCodexMessagesCountedAccurately() throws Exception {
    String sessionId1 = "thread-day1";
    String sessionId2 = "thread-day2";

    // 第一日：2 条用户消息
    createCodexRollout(
        sessionId1,
        "2026",
        "09",
        "05",
        """
        {"type":"event_msg","timestamp":"2026-09-05T10:00:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"event_msg","timestamp":"2026-09-05T10:01:00Z","payload":{"type":"agent_message","content":"hi"}}
        {"type":"event_msg","timestamp":"2026-09-05T10:02:00Z","payload":{"type":"user_message","message":"how are you"}}
        {"type":"event_msg","timestamp":"2026-09-05T10:03:00Z","payload":{"type":"agent_message","content":"good"}}
        """);

    // 第二日：3 条用户消息
    createCodexRollout(
        sessionId2,
        "2026",
        "09",
        "06",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"agent_message","content":"hi"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"user_message","message":"how are you"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:03:00Z","payload":{"type":"agent_message","content":"good"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:04:00Z","payload":{"type":"user_message","message":"thanks"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:05:00Z","payload":{"type":"agent_message","content":"welcome"}}
        """);

    var discovered = adapter.discover(tempDir);

    processAndWriteCodexSession(discovered, sessionId1, "2026-09-05T10:03:00Z");
    processAndWriteCodexSession(discovered, sessionId2, "2026-09-06T10:05:00Z");

    TrendFilter filter = fixtureWindow();
    List<ActivityTrend> trends = queryRepository.activityTrend(filter);

    // 验证：两日分别有 2 和 3 条 Codex 用户消息
    assertThat(trends).hasSize(2);
    ActivityTrend day1 = trends.get(0);
    ActivityTrend day2 = trends.get(1);

    assertThat(day1.date()).isEqualTo("2026-09-05");
    assertThat(day1.codexPrompts()).isEqualTo(2L);
    assertThat(day1.totalPrompts()).isEqualTo(2L);

    assertThat(day2.date()).isEqualTo("2026-09-06");
    assertThat(day2.codexPrompts()).isEqualTo(3L);
    assertThat(day2.totalPrompts()).isEqualTo(3L);
  }

  @Test
  @DisplayName("零消息会话不增加 Prompt 计数")
  void zeroMessageSessionDoesNotIncreasePromptCount() throws Exception {
    assertPromptCount(
        "thread-empty",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"agent_message","content":"hi"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"agent_message","content":"how can I help"}}
        """,
        0L);
  }

  @Test
  @DisplayName("双表示共存时只计数一次")
  void dualRepresentationCountedOnce() throws Exception {
    assertPromptCount(
        "thread-dual",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        {"type":"event_msg","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"agent_message","content":"hi"}}
        """,
        1L);
  }

  @Test
  @DisplayName("仅有 eventType=user 时正常计数")
  void userEventTypeCountedWhenNoEventMsg() throws Exception {
    assertPromptCount(
        "thread-response-item",
        """
        {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"thanks"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:03:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"welcome"}]}}
        """,
        2L);
  }

  @Test
  @DisplayName("相同文本不同轮次分别计数")
  void repeatedTextCountedSeparately() throws Exception {
    assertPromptCount(
        "thread-repeated",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"agent_message","content":"hi"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:03:00Z","payload":{"type":"agent_message","content":"hi again"}}
        """,
        2L);
  }

  @Test
  @DisplayName("UTC 偏移会话按 started_at 归属日期")
  void utcOffsetSessionAttributedByStartedAt() throws Exception {
    // 本地日期 09-07，UTC 日期 09-06；查询必须转换 offset，而非截取日期。
    String sessionId = "thread-utc";
    createCodexRollout(
        sessionId,
        "2026",
        "09",
        "06",
        """
        {"type":"event_msg","timestamp":"2026-09-07T07:00:00+08:00","payload":{"type":"user_message","message":"hello"}}
        {"type":"event_msg","timestamp":"2026-09-07T07:30:00+08:00","payload":{"type":"agent_message","content":"hi"}}
        """);

    var discovered = adapter.discover(tempDir);

    processAndWriteCodexSession(discovered, sessionId, "2026-09-07T07:30:00+08:00");

    TrendFilter filter = fixtureWindow();
    List<ActivityTrend> trends = queryRepository.activityTrend(filter);

    // 验证：按 UTC started_at 归属到 2026-09-06；开始/结束在同一 UTC 日。
    assertThat(trends).hasSize(1);
    assertThat(trends.get(0).date()).isEqualTo("2026-09-06");
    assertThat(trends.get(0).codexPrompts()).isEqualTo(1L);
  }

  @Test
  @DisplayName("混合双表示与独立 response-only 轮次均保留")
  void mixedRepresentationKeepsIndependentResponseOnlyTurn() throws Exception {
    assertPromptCount(
        "thread-mixed",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"hello"}}
        {"type":"response_item","timestamp":"2026-09-06T10:00:01Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        """,
        2L);
  }

  @Test
  @DisplayName("累计 usage 下 assistant response_item 仍隔开重复 prompt")
  void cumulativeUsageAssistantSeparatesRepeatedPrompts() throws Exception {
    assertPromptCount(
        "thread-cumulative-boundary",
        """
        {"type":"event_msg","timestamp":"2026-09-06T09:59:00Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12}}}}
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"again"}}
        {"type":"response_item","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"again"}]}}
        """,
        2L);
  }

  @Test
  @DisplayName("task 生命周期边界不合并前后相同 prompt")
  void taskLifecycleSeparatesRepeatedPrompts() throws Exception {
    assertPromptCount(
        "thread-task-boundary",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"again"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"task_complete","turn_id":"turn-one"}}
        {"type":"event_msg","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"task_started","turn_id":"turn-two"}}
        {"type":"response_item","timestamp":"2026-09-06T10:03:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"again"}]}}
        """,
        2L);
  }

  @Test
  @DisplayName("缺 timestamp 的重复轮次计数保留，但不参与日期趋势")
  void missingTimestampsDoNotLoseRepeatedTurns() throws Exception {
    String sessionId = "thread-no-timestamp";
    createCodexRollout(
        sessionId,
        "2026",
        "09",
        "06",
        """
        {"type":"event_msg","payload":{"type":"user_message","message":"hello"}}
        {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}}
        {"type":"event_msg","payload":{"type":"user_message","message":"hello"}}
        {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"hello"}]}}
        """);
    processAndWriteCodexSession(adapter.discover(tempDir), sessionId, "2026-09-06T10:03:00Z");

    // 路径日期和测试注入的 ended_at 不是实际开始时间；两轮相同 prompt 仍精确计为 2。
    try (var statement =
        connection.prepareStatement(
            "SELECT started_at, user_message_count FROM sessions WHERE session_id = ?")) {
      statement.setString(1, sessionId);
      try (var row = statement.executeQuery()) {
        assertThat(row.next()).isTrue();
        assertThat(row.getString("started_at")).isEmpty();
        assertThat(row.getLong("user_message_count")).isEqualTo(2L);
        assertThat(row.next()).isFalse();
      }
    }
    assertThat(queryRepository.activityTrend(fixtureWindow())).isEmpty();
    assertThat(queryRepository.trendData(fixtureWindow())).isEmpty();
  }

  @Test
  @DisplayName("相同 timestamp 的不同 prompt 不合并")
  void sameTimestampDifferentPromptsRemainSeparate() throws Exception {
    assertPromptCount(
        "thread-same-timestamp",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"first"}}
        {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"second"}]}}
        """,
        2L);
  }

  @Test
  @DisplayName("旧 logic 5 未变源索引经普通扫描修复且下一轮不重写")
  void oldScanLogicRepairsZeroCountThenRemainsUnchanged() throws Exception {
    String sessionId = "thread-old-index";
    createCodexRollout(
        sessionId,
        "2026",
        "09",
        "06",
        """
        {"type":"event_msg","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"user_message","message":"first"}}
        {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"first"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:01:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hi"}]}}
        {"type":"response_item","timestamp":"2026-09-06T10:02:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"second"}]}}
        """);
    Path source = tempDir.resolve("sessions/2026/09/06/rollout-100-" + sessionId + ".jsonl");
    byte[] sourceBytes = Files.readAllBytes(source);
    var sourceFingerprint = adapter.fingerprint(source);
    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(adapter, tempDir)), tempDir.resolve("artifacts"));
    var initial = scanEngineAt("2026-09-06T11:00:00Z").scan(indexWriter, config);
    assertThat(initial.issues()).isEmpty();
    assertThat(initial.newCount()).isEqualTo(1);

    // 模拟真实旧索引状态；不改源文件或指纹，也不手工执行 normalize。
    try (var statement = connection.createStatement()) {
      assertThat(
              statement.executeUpdate("UPDATE sessions SET user_message_count = 0, indexed_at = 1"))
          .isEqualTo(1);
    }
    indexWriter.saveScanLogicVersion(5, Instant.parse("2026-09-06T11:00:00Z"));
    indexWriter.flushPendingWrites();
    assertThat(indexWriter.loadScanLogicVersion()).isEqualTo(5);
    assertThat(queryRepository.activityTrend(fixtureWindow()))
        .singleElement()
        .satisfies(trend -> assertThat(trend.codexPrompts()).isZero());

    // 源内容、mtime 和源指纹均未变化，普通 scan 必须仅由旧版本失效触发重算。
    assertThat(Files.readAllBytes(source)).isEqualTo(sourceBytes);
    assertThat(adapter.fingerprint(source)).isEqualTo(sourceFingerprint);
    var repaired = scanEngineAt("2026-09-06T12:00:00Z").scan(indexWriter, config);
    assertThat(repaired.issues()).isEmpty();
    assertThat(repaired.newCount() + repaired.changedCount()).isEqualTo(1);
    assertThat(repaired.unchangedCount()).isZero();
    assertThat(indexWriter.loadScanLogicVersion())
        .isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION)
        .isGreaterThan(5);
    assertThat(queryRepository.activityTrend(fixtureWindow()))
        .singleElement()
        .satisfies(
            trend -> {
              assertThat(trend.codexPrompts()).isEqualTo(2L);
              assertThat(trend.totalPrompts()).isEqualTo(2L);
            });
    double repairedIndexedAt = indexedAt();
    assertThat(repairedIndexedAt).isGreaterThan(1.0);

    var unchanged = scanEngineAt("2026-09-06T13:00:00Z").scan(indexWriter, config);
    assertThat(unchanged.issues()).isEmpty();
    assertThat(unchanged.unchangedCount()).isEqualTo(1);
    assertThat(unchanged.newCount()).isZero();
    assertThat(unchanged.changedCount()).isZero();
    assertThat(indexedAt()).isEqualTo(repairedIndexedAt);
    assertThat(Files.readAllBytes(source)).isEqualTo(sourceBytes);
    assertThat(adapter.fingerprint(source)).isEqualTo(sourceFingerprint);
    assertThat(indexWriter.loadScanLogicVersion())
        .isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);
  }

  private IncrementalScanEngine scanEngineAt(String instant) {
    return new IncrementalScanEngine(
        normalizationEngine,
        new NormalizedArtifactWriter(),
        Clock.fixed(Instant.parse(instant), ZoneOffset.UTC));
  }

  private double indexedAt() throws Exception {
    try (var statement = connection.createStatement();
        var rows = statement.executeQuery("SELECT indexed_at FROM sessions")) {
      assertThat(rows.next()).isTrue();
      double value = rows.getDouble(1);
      assertThat(rows.next()).isFalse();
      return value;
    }
  }

  private void assertPromptCount(String sessionId, String content, long expected) throws Exception {
    createCodexRollout(sessionId, "2026", "09", "06", content);
    processAndWriteCodexSession(adapter.discover(tempDir), sessionId, "2026-09-06T10:03:00Z");
    assertThat(queryRepository.activityTrend(fixtureWindow()))
        .singleElement()
        .satisfies(
            trend -> {
              assertThat(trend.codexPrompts()).isEqualTo(expected);
              assertThat(trend.totalPrompts()).isEqualTo(expected);
            });
  }

  private static TrendFilter fixtureWindow() {
    // 固定合成日期仍可断言精确分桶；回溯窗口随 UTC 当前日期增长，避免测试七天后失效。
    long age = ChronoUnit.DAYS.between(LocalDate.of(2026, 9, 5), LocalDate.now(ZoneOffset.UTC));
    return TrendFilter.ofDays(Math.toIntExact(Math.max(7L, age + 2)));
  }

  private void createCodexRollout(
      String sessionId, String year, String month, String day, String content) throws IOException {
    // 追加写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve("session_index.jsonl"),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Test Thread\",\"updated_at\":\"2026-09-06\"}\n",
        StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.APPEND);

    // 创建 rollout 文件
    Path dayDir = tempDir.resolve("sessions").resolve(year).resolve(month).resolve(day);
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(rollout, content, StandardCharsets.UTF_8);
  }

  private void processAndWriteCodexSession(
      com.feipi.session.browser.source.spi.BoundedStream<Candidate> discovered,
      String sessionId,
      String endedAt)
      throws Exception {
    Candidate candidate =
        discovered.orderedItems().stream()
            .filter(c -> c.sessionKey().equals("codex:" + sessionId))
            .findFirst()
            .orElseThrow();

    SourceResult result = adapter.parse(candidate, null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    SourceResult.Success success = (SourceResult.Success) result;

    NormalizedSessionArtifact artifact =
        normalizationEngine.normalize(
            NormalizedAgent.CODEX, success.records(), success.diagnostics(), List.of());

    // 注入 candidate 元数据到 session map（归一化引擎是纯函数，不含源特定标识）
    String safeSessionKey = candidate.sessionKey().replace('/', ':');
    Map<String, Object> enrichedSession = new java.util.LinkedHashMap<>(artifact.session());
    enrichedSession.put("session_key", safeSessionKey);
    enrichedSession.put("session_id", sessionId);
    enrichedSession.put("ended_at", endedAt);
    enrichedSession.put("project_key", "test-project");
    enrichedSession.put("project_name", "Test Project");
    enrichedSession.put("cwd", "/test");

    NormalizedSessionArtifact enrichedArtifact =
        new NormalizedSessionArtifact(
            artifact.schemaVersion(),
            artifact.agent(),
            artifact.sourceFiles(),
            enrichedSession,
            artifact.calls(),
            artifact.toolExecutions(),
            artifact.diagnostics(),
            java.util.Map.of(),
            java.util.Map.of());

    Path artifactPath = tempDir.resolve("artifacts").resolve(sessionId + ".json");
    Files.createDirectories(artifactPath.getParent());
    indexWriter.writeNormalizedArtifact(
        enrichedArtifact,
        artifactPath,
        candidate.fingerprint().locator(),
        0.0,
        0L,
        Instant.parse(endedAt));
    indexWriter.flushPendingWrites();
  }
}
