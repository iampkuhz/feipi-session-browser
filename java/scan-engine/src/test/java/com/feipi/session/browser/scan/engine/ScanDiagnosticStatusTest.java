package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
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
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.slf4j.LoggerFactory;

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
  void fatalSourceCodeAndItsLineDiagnosticsReachBothScanModesAndFailureLog() throws Exception {
    for (boolean incremental : List.of(false, true)) {
      String name = "fatal-source-" + incremental;
      try (var connection =
          DriverManager.getConnection("jdbc:sqlite:" + directory.resolve(name + ".db"))) {
        var writer = new SqliteIndexWriter(connection);
        var config =
            config(
                name,
                ignored ->
                    new SourceResult.Fatal(
                        List.of(diagnostic(ParseSeverity.ERROR)),
                        "fixture-sensitive-path /private/fixture",
                        "CODEX_HISTORY_PARENT_CONFLICT"));
        var issues =
            incremental
                ? new IncrementalScanEngine().scan(writer, config).issues()
                : new FullScanEngine().scan(writer, config).issues();
        assertThat(issues).hasSize(1);
        assertThat(ScanDiagnostics.failures(issues))
            .satisfiesExactly(
                fatal -> {
                  assertThat(fatal.code()).isEqualTo("CODEX_HISTORY_PARENT_CONFLICT");
                  assertThat(fatal.line()).isZero();
                },
                diagnostic -> {
                  assertThat(diagnostic.code()).isEqualTo("BUFFER_OVERFLOW");
                  assertThat(diagnostic.line()).isEqualTo(42);
                });
        assertThat(issues.toString()).doesNotContain("fixture-sensitive");
        assertThat(persistedFailures(connection))
            .contains("CODEX_HISTORY_PARENT_CONFLICT", "BUFFER_OVERFLOW")
            .doesNotContain("fixture-sensitive");
      }
    }
  }

  @Test
  void jvmErrorReportsOneSafeContextAndRollsBackInBothScanModes() throws Exception {
    var logger = (Logger) LoggerFactory.getLogger(ScanFatalDiagnostics.class);
    var logs = new ListAppender<ILoggingEvent>();
    logs.start();
    logger.addAppender(logs);
    try {
      for (boolean incremental : List.of(false, true)) {
        String name = "fatal-jvm-" + incremental;
        try (var connection =
            DriverManager.getConnection("jdbc:sqlite:" + directory.resolve(name + ".db"))) {
          var writer = new SqliteIndexWriter(connection);
          writer.ensureSchema();
          long initial = writer.startScan(0, "full");
          writer.writeMissingTranscriptSession(
              new MissingTranscriptSession(
                  "codex:old", "codex", "old", "Old", "", "", "", "", "", "codex", Instant.EPOCH));
          writer.saveScanLogicVersion(
              IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION, Instant.EPOCH);
          writer.completeScan(initial, 1, Map.of("codex", 1));
          var fatal = new OutOfMemoryError("fixture-sensitive-path /private/fixture");
          var config =
              config(
                  name,
                  ignored -> {
                    throw fatal;
                  });
          logs.list.clear();
          if (incremental) {
            var scanner =
                new BackgroundScanner(
                    TierConfig.DEFAULT_HOT,
                    TierConfig.DEFAULT_WARM,
                    new ScanLock(directory),
                    token -> new IncrementalScanEngine().scan(writer, config),
                    token -> new IncrementalScanEngine().scan(writer, config),
                    Clock.systemUTC());
            try {
              assertThatThrownBy(scanner::checkAndScanSafe).isSameAs(fatal);
              assertThat(scanner.hasFatalError()).isTrue();
            } finally {
              scanner.shutdown();
            }
          } else {
            assertThatThrownBy(() -> new FullScanEngine().scan(writer, config)).isSameAs(fatal);
          }
          assertThat(logs.list)
              .singleElement()
              .satisfies(
                  event -> {
                    assertThat(event.getFormattedMessage())
                        .contains(
                            "severity=FATAL",
                            "scanLogId=2",
                            "phase=CANDIDATE",
                            "source=codex",
                            "code=SCAN_JVM_OUT_OF_MEMORY",
                            "java.lang.OutOfMemoryError",
                            "frames=[",
                            "hint=")
                        .doesNotContain("fixture-sensitive", "/private/fixture");
                    assertThat(event.getThrowableProxy()).isNull();
                  });
          assertThat(persistedFailures(connection)).contains("SCAN_JVM_OUT_OF_MEMORY", "CANDIDATE");
          assertThat(writer.loadStoredSessionFingerprints()).containsOnlyKeys("codex:old");
        }
      }
    } finally {
      ScanFatalDiagnostics.clearReported();
      logger.detachAppender(logs);
      logs.stop();
    }
  }

  private static String persistedFailures(java.sql.Connection connection) throws Exception {
    try (var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT status, failures_json FROM scan_log ORDER BY id DESC LIMIT 1")) {
      assertThat(rows.next()).isTrue();
      assertThat(rows.getString("status")).isEqualTo("failure");
      return rows.getString("failures_json");
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
    var diagnostic = diagnostic(severity);
    return config(
        name,
        fingerprint ->
            new SourceResult.Success(
                severity == ParseSeverity.ERROR
                    ? List.of(diagnostic, diagnostic)
                    : List.of(diagnostic),
                1,
                List.of(),
                fingerprint,
                null));
  }

  private ScanConfig config(String name, Function<SourceFingerprint, SourceResult> parse)
      throws Exception {
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
            return parse.apply(fingerprint);
          }
        };
    return ScanConfig.defaults(
        List.of(new ScanConfig.SourceEntry(adapter, root)), directory.resolve("artifacts-" + name));
  }

  private static SourceDiagnostic diagnostic(ParseSeverity severity) {
    return new SourceDiagnostic(
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
  }
}
