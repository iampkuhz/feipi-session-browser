package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ScanDiagnosticStatusTest {
  @TempDir Path directory;

  @Test
  void unresolvedToolOwnerHasAnExactSafeReasonWithoutCopyingExceptionText() {
    var failures =
        ScanDiagnostics.failures(
            List.of(
                new ScanIssue(
                    "codex:synthetic",
                    "codex",
                    ScanIssue.ScanPhase.NORMALIZE,
                    "TOOL_OWNER_UNAVAILABLE"),
                new ScanIssue(
                    "codex:synthetic",
                    "codex",
                    ScanIssue.ScanPhase.NORMALIZE,
                    "TOOL_OWNER_UNAVAILABLE: fixture-sensitive-message"),
                new ScanIssue(
                    "codex:synthetic",
                    "codex",
                    ScanIssue.ScanPhase.PARSE,
                    "TOOL_OWNER_UNAVAILABLE")));
    assertThat(failures)
        .extracting(failure -> failure.code())
        .containsExactly("TOOL_OWNER_UNAVAILABLE", "NORMALIZE_FAILED", "PARSE_FAILED");
    assertThat(failures.toString()).doesNotContain("fixture-sensitive-message");
  }

  @Test
  void successWithErrorDiagnosticsFailsBothScanModesAndRetainsPreviousIndex() throws Exception {
    for (boolean incremental : List.of(false, true)) {
      try (var connection =
          DriverManager.getConnection(
              "jdbc:sqlite:" + directory.resolve("error-" + incremental + ".db"))) {
        var writer = new SqliteIndexWriter(connection);
        writer.ensureSchema();
        long initial = writer.startScan(0, "full");
        writer.writeMissingTranscriptSession(
            new MissingTranscriptSession(
                "codex:old", "codex", "old", "Old", "", "", "", "", "", "codex", Instant.EPOCH));
        writer.saveScanLogicVersion(
            IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION, Instant.EPOCH);
        writer.completeScan(initial, 1, Map.of("codex", 1));
        var config = config("error-" + incremental, ParseSeverity.ERROR);
        int errors =
            incremental
                ? new IncrementalScanEngine().scan(writer, config).errorCount()
                : new FullScanEngine().scan(writer, config).errorCount();
        assertThat(errors).isEqualTo(1);
        assertThat(writer.loadStoredSessionFingerprints()).containsOnlyKeys("codex:old");
        try (var statement = connection.createStatement();
            var rows =
                statement.executeQuery(
                    "SELECT status,error_count,failures_json,json_array_length(failures_json) AS"
                        + " diagnostic_count FROM scan_log ORDER BY id DESC LIMIT 1")) {
          assertThat(rows.next()).isTrue();
          assertThat(rows.getString("status")).isEqualTo("failure");
          assertThat(rows.getInt("error_count")).isEqualTo(errors);
          assertThat(rows.getInt("diagnostic_count")).isEqualTo(2);
          assertThat(rows.getString("failures_json"))
              .contains("BUFFER_OVERFLOW", "PARSE", "42")
              .doesNotContain("fixture-sensitive-preview", "fixture-sensitive-message");
        }
      }
    }
  }

  @Test
  void informationalAndRecoverableWarningsDoNotBecomeScanFailures() throws Exception {
    for (ParseSeverity severity : List.of(ParseSeverity.INFO, ParseSeverity.WARNING)) {
      try (var connection =
          DriverManager.getConnection(
              "jdbc:sqlite:" + directory.resolve(severity.name() + ".db"))) {
        var writer = new SqliteIndexWriter(connection);
        var summary = new FullScanEngine().scan(writer, config(severity.name(), severity));
        assertThat(summary.errorCount()).isZero();
        assertThat(summary.isFullySuccessful()).isTrue();
      }
    }
  }

  private ScanConfig config(String name, ParseSeverity severity) throws Exception {
    Path root = Files.createDirectories(directory.resolve(name));
    Path source = Files.writeString(root.resolve("synthetic.jsonl"), "synthetic fixture");
    var fingerprint =
        new SourceFingerprint(
            source.toString(),
            SourceId.CODEX,
            Files.size(source),
            1000,
            Optional.empty(),
            Optional.empty());
    var candidate = new Candidate(fingerprint, "codex:new", "project", Map.of());
    SourceAdapter adapter =
        new SourceAdapter() {
          @Override
          public SourceId sourceId() {
            return SourceId.CODEX;
          }

          @Override
          public BoundedStream<Candidate> discover(Path path) {
            return BoundedStream.of(
                List.of(candidate), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
          }

          @Override
          public SourceFingerprint fingerprint(Path path) {
            return fingerprint;
          }

          @Override
          public SourceResult parse(Candidate item, CancellationSignal cancellation) {
            var diagnostic =
                new SourceDiagnostic(
                    severity,
                    ParseIssueType.BAD_JSON,
                    "fixture-sensitive-message",
                    42,
                    Optional.of("fixture-sensitive-preview"),
                    "BAD_JSON:BUFFER_OVERFLOW",
                    "fixture",
                    null,
                    null,
                    null);
            return new SourceResult.Success(
                severity == ParseSeverity.ERROR
                    ? List.of(diagnostic, diagnostic)
                    : List.of(diagnostic),
                1,
                List.of(),
                fingerprint,
                null);
          }
        };
    return ScanConfig.defaults(
        List.of(new ScanConfig.SourceEntry(adapter, root)), directory.resolve("artifacts-" + name));
  }
}
