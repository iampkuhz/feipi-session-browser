package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ContentPersistenceTest {
  @TempDir Path tempDir;

  @Test
  void oneLogicalSessionAndAssociationPublishAndRollbackTogether() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("content.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      var writer = new SqliteIndexWriter(connection.writerConnection());
      writer.ensureSchema();
      long scan = writer.startScan(1, "full");
      writer.writeNormalizedContent(
          content(10234), tempDir.resolve("content.json"), "synthetic.jsonl", 3, 9, Instant.EPOCH);
      writer.completeScan(scan, 2, Map.of("codex", 1));
      try (var stmt = connection.writerConnection().createStatement();
          var result =
              stmt.executeQuery("SELECT llm_call_count, round_count, total_tokens FROM sessions")) {
        assertThat(result.next()).isTrue();
        assertThat(result.getLong(1)).isEqualTo(10234);
        assertThat(result.getLong(2)).isEqualTo(10234);
        assertThat(result.getLong(3)).isEqualTo(10234);
        assertThat(result.next()).isFalse();
      }
      scan = writer.startScan(3, "incremental");
      writer.writeNormalizedContent(
          content(1), tempDir.resolve("replacement.json"), "synthetic.jsonl", 4, 10, Instant.EPOCH);
      writer.flushPendingWrites();
      writer.failScan(scan, 4, Map.of());
      try (var stmt = connection.writerConnection().createStatement();
          var result = stmt.executeQuery("SELECT path FROM session_artifacts")) {
        assertThat(result.next()).isTrue();
        assertThat(result.getString(1)).endsWith("content.json");
        assertThat(result.next()).isFalse();
      }
      assertThat(
              writer
                  .loadStoredSessionFingerprints()
                  .get("codex:large")
                  .candidateMetadataFingerprint())
          .isEqualTo("synthetic-fingerprint");
    }
  }

  @Test
  void failedTraversalDoesNotEnqueuePartialSessionOrAssociation() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("failure.db");
    try (var connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      var writer = new SqliteIndexWriter(connection.writerConnection());
      writer.ensureSchema();
      var valid = content(2);
      var broken =
          new NormalizedSessionContent() {
            @Override
            public NormalizedContentHeader header() {
              return valid.header();
            }

            @Override
            public ContentCursor openCursor() throws java.io.IOException {
              var cursor = valid.openCursor();
              return new ContentCursor() {
                private boolean consumed;

                @Override
                public boolean hasNext() throws java.io.IOException {
                  if (consumed) throw new java.io.IOException("synthetic truncated content");
                  return cursor.hasNext();
                }

                @Override
                public NormalizedContentUnit next() throws java.io.IOException {
                  consumed = true;
                  return cursor.next();
                }

                @Override
                public void close() throws java.io.IOException {
                  cursor.close();
                }
              };
            }
          };
      assertThatThrownBy(
              () ->
                  writer.writeNormalizedContent(
                      broken,
                      tempDir.resolve("broken.json"),
                      "synthetic.jsonl",
                      0,
                      1,
                      Instant.EPOCH))
          .isInstanceOf(java.io.IOException.class);
      assertThat(writer.pendingWriteCount()).isZero();
      try (var statement = connection.writerConnection().createStatement();
          var result = statement.executeQuery("SELECT count(*) FROM sessions")) {
        assertThat(result.next()).isTrue();
        assertThat(result.getInt(1)).isZero();
      }
    }
  }

  private static NormalizedSessionContent content(int size) {
    var calls =
        IntStream.rangeClosed(1, size)
            .mapToObj(
                i ->
                    new NormalizedCall(
                        "c" + i,
                        i,
                        "C" + i,
                        CallScope.MAIN,
                        Optional.empty(),
                        Optional.empty(),
                        Optional.of("t" + i),
                        "model",
                        Optional.empty(),
                        new NormalizedCallUsage(0, 0, 0, 1, 1),
                        NormalizedCallRequest.empty(),
                        NormalizedCallResponse.empty(),
                        List.of(),
                        List.of(),
                        Map.of(),
                        Map.of()))
            .toList();
    var header =
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            NormalizedSessionMetadata.fromMap(
                Map.of(
                    "session_key",
                    "codex:large",
                    "session_id",
                    "large",
                    "candidate_metadata_fingerprint",
                    "synthetic-fingerprint")),
            Map.of(
                "calls",
                (long) size,
                "toolExecutions",
                0L,
                "diagnostics",
                0L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                0L,
                "sourceUnitSequenceEntries",
                0L));
    return NormalizedSessionContent.fromLists(
        header, List.of(), calls, List.of(), List.of(), Map.of(), Map.of());
  }
}
