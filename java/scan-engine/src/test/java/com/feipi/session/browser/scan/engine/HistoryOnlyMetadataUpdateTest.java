package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * History-only 会话元数据更新集成测试。
 *
 * <p>验证真实 SQLite 写入路径：metadata-only 第一次导入、第二次无改动 write=0/unchanged， 单独改 title、projectKey/cwd、
 * timestamp、transcript 补齐均实际更新。 断言实际写入次数而非仅日志。
 */
class HistoryOnlyMetadataUpdateTest {

  @TempDir Path tempDir;

  private Connection conn;
  private SqliteIndexWriter writer;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    conn.setAutoCommit(false);
    writer = new SqliteIndexWriter(conn);
    writer.ensureSchema();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void finalFlushFailureIsVisibleToBootstrap() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);
    Candidate candidate = makeHistoryOnlyCandidate("session-1", "Title", "/project", "/cwd", 1000L);
    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate)), root)),
            tempDir.resolve("artifacts"));
    var portType = com.feipi.session.browser.index.api.write.IndexWriterPort.class;
    var failing =
        (com.feipi.session.browser.index.api.write.IndexWriterPort)
            java.lang.reflect.Proxy.newProxyInstance(
                portType.getClassLoader(),
                new Class<?>[] {portType},
                (proxy, method, args) -> {
                  if (method.getName().equals("flushPendingWrites")) {
                    throw new IllegalStateException("synthetic flush failure");
                  }
                  return method.invoke(writer, args);
                });
    var result = new IncrementalScanEngine().scan(failing, config);
    assertThat(result.issues())
        .anySatisfy(issue -> assertThat(issue.phase()).isEqualTo(ScanIssue.ScanPhase.INDEX_WRITE));
  }

  @Test
  void secondScanWithNoChangesWritesZero() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    Candidate candidate = makeHistoryOnlyCandidate("session-1", "Title", "/project", "/cwd", 1000L);
    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    IncrementalScanSummary summary1 = engine.scan(writer, config);
    conn.commit();

    assertThat(summary1.newCount()).isEqualTo(1);
    assertThat(summary1.unchangedCount()).isZero();

    IncrementalScanSummary summary2 = engine.scan(writer, config);
    conn.commit();

    assertThat(summary2.newCount()).isZero();
    assertThat(summary2.unchangedCount()).isEqualTo(1);
    assertThat(summary2.changedCount()).isZero();
  }

  @Test
  void titleChangeTriggersUpdate() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    Candidate candidate1 =
        makeHistoryOnlyCandidate("session-1", "Old Title", "/project", "/cwd", 1000L);
    ScanConfig config1 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate1)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(writer, config1);
    conn.commit();

    Candidate candidate2 =
        makeHistoryOnlyCandidate("session-1", "New Title", "/project", "/cwd", 1000L);
    ScanConfig config2 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate2)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanSummary summary = engine.scan(writer, config2);
    conn.commit();

    assertThat(summary.changedCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isZero();

    var fingerprints = writer.loadStoredSessionFingerprints();
    assertThat(fingerprints.get("claude_code:session-1").title()).isEqualTo("New Title");
  }

  @Test
  void projectKeyChangeTriggersUpdate() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    // projectKey 由 meaningfulProject(cwd, candidate.projectKey()) 派生
    // 当 cwd 无意义（如 "."）时，使用 candidate.projectKey()
    // 保持 cwd 不变（无意义），仅改变 candidate.projectKey()
    Candidate candidate1 =
        makeHistoryOnlyCandidate("session-1", "Title", "/old/project", ".", 1000L);
    ScanConfig config1 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate1)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(writer, config1);
    conn.commit();

    Candidate candidate2 =
        makeHistoryOnlyCandidate("session-1", "Title", "/new/project", ".", 1000L);
    ScanConfig config2 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate2)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanSummary summary = engine.scan(writer, config2);
    conn.commit();

    assertThat(summary.changedCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isZero();

    var fingerprints = writer.loadStoredSessionFingerprints();
    assertThat(fingerprints.get("claude_code:session-1").projectKey()).isEqualTo("/new/project");
  }

  @Test
  void cwdChangeTriggersUpdate() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    Candidate candidate1 =
        makeHistoryOnlyCandidate("session-1", "Title", "/project", "/old/cwd", 1000L);
    ScanConfig config1 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate1)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(writer, config1);
    conn.commit();

    Candidate candidate2 =
        makeHistoryOnlyCandidate("session-1", "Title", "/project", "/new/cwd", 1000L);
    ScanConfig config2 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate2)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanSummary summary = engine.scan(writer, config2);
    conn.commit();

    assertThat(summary.changedCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isZero();

    var fingerprints = writer.loadStoredSessionFingerprints();
    assertThat(fingerprints.get("claude_code:session-1").cwd()).isEqualTo("/new/cwd");
  }

  @Test
  void timestampChangeTriggersUpdate() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    Candidate candidate1 =
        makeHistoryOnlyCandidate("session-1", "Title", "/project", "/cwd", 1000L);
    ScanConfig config1 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate1)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(writer, config1);
    conn.commit();

    Candidate candidate2 =
        makeHistoryOnlyCandidate("session-1", "Title", "/project", "/cwd", 2000L);
    ScanConfig config2 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate2)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanSummary summary = engine.scan(writer, config2);
    conn.commit();

    assertThat(summary.changedCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isZero();
  }

  @Test
  void transcriptLaterAppearsTriggersUpdate() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);
    Path transcriptFile = root.resolve("session-1.jsonl");
    Files.writeString(transcriptFile, "initial");

    Candidate candidate1 = makeHistoryOnlyCandidate("session-1", "Title", "/project", "/cwd", 0L);
    ScanConfig config1 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate1)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(writer, config1);
    conn.commit();

    var fingerprints1 = writer.loadStoredSessionFingerprints();
    assertThat(fingerprints1.get("claude_code:session-1").filePath()).isEmpty();

    Files.writeString(transcriptFile, "real transcript content");
    Candidate candidate2 = makeCandidateWithTranscript("session-1", transcriptFile, 1000L);
    ScanConfig config2 =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new HistoryOnlyAdapter(List.of(candidate2)), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanSummary summary = engine.scan(writer, config2);
    conn.commit();

    assertThat(summary.changedCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isZero();

    var fingerprints2 = writer.loadStoredSessionFingerprints();
    assertThat(fingerprints2.get("claude_code:session-1").filePath()).isNotEmpty();
  }

  private Candidate makeHistoryOnlyCandidate(
      String sessionId, String title, String projectKey, String cwd, long timestampMs) {
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            "history.jsonl", SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    return new Candidate(
        fingerprint,
        "claude_code:" + sessionId,
        projectKey,
        Map.of("title", title, "cwd", cwd, "timestamp", String.valueOf(timestampMs)));
  }

  private Candidate makeCandidateWithTranscript(
      String sessionId, Path transcriptFile, long mtimeMs) {
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            transcriptFile.toString(),
            SourceId.CLAUDE_CODE,
            100,
            mtimeMs,
            Optional.of("hash"),
            Optional.empty());
    return new Candidate(fingerprint, "claude_code:" + sessionId, "/project", Map.of());
  }

  /** 测试用 SourceAdapter，返回预定义的 history-only 候选项。 */
  private static class HistoryOnlyAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    HistoryOnlyAdapter(List<Candidate> candidates) {
      this.candidates = List.copyOf(candidates);
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, SourceAdapter.CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }
}
