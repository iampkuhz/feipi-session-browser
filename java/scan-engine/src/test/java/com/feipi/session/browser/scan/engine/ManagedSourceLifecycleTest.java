package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.index.api.write.IndexWriterPort;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.NormalizedArtifactWriter;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 有管理源的所有权覆盖成功及各阶段失败；小调用数不能触发正文全量物化。 */
class ManagedSourceLifecycleTest {
  @TempDir Path directory;

  @Test
  void smallManagedSourceUsesUnitsAndStaysOpenThroughWriterAndIndexReplay() throws Exception {
    var sequence = new OwnedRecords();
    var writes = new AtomicInteger();
    var result = process(sequence, List.of(), directory, false, writes);
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.SUCCESS);
    assertThat(sequence.closes).isEqualTo(1);
    assertThat(writes).hasValue(1);
  }

  @Test
  void sourceErrorsCloseBeforeNormalizationAndKeepPrimaryFailure() throws Exception {
    var sequence = new OwnedRecords();
    sequence.failClose = true;
    var diagnostic =
        new SourceDiagnostic(
            ParseSeverity.ERROR,
            ParseIssueType.BAD_JSON,
            "synthetic-source-error",
            1,
            Optional.empty(),
            "SYNTHETIC_ERROR",
            "synthetic",
            java.util.OptionalInt.empty(),
            java.util.OptionalInt.empty(),
            java.util.OptionalInt.empty());
    var result = process(sequence, List.of(diagnostic), directory, false, new AtomicInteger());
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.ERROR);
    assertThat(result.phase()).isEqualTo(ScanIssue.ScanPhase.PARSE);
    assertThat(result.message()).contains("SOURCE_ERRORS");
    assertThat(sequence.closes).isEqualTo(1);
    assertThat(sequence.opens).isZero();
  }

  @Test
  void normalizationReadFailureClosesTheSource() throws Exception {
    var sequence = new OwnedRecords();
    sequence.failRead = true;
    var result = process(sequence, List.of(), directory, false, new AtomicInteger());
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.ERROR);
    assertThat(result.phase()).isEqualTo(ScanIssue.ScanPhase.NORMALIZE);
    assertThat(result.message()).contains("synthetic-read-failure");
    assertThat(sequence.closes).isEqualTo(1);
  }

  @Test
  void artifactWriteFailureClosesTheSource() throws Exception {
    var sequence = new OwnedRecords();
    Path blocked = Files.writeString(directory.resolve("blocked"), "synthetic");
    var result = process(sequence, List.of(), blocked, false, new AtomicInteger());
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.ERROR);
    assertThat(result.phase()).isEqualTo(ScanIssue.ScanPhase.ARTIFACT_WRITE);
    assertThat(sequence.closes).isEqualTo(1);
  }

  @Test
  void indexFailureClosesTheSource() throws Exception {
    var sequence = new OwnedRecords();
    var result = process(sequence, List.of(), directory, true, new AtomicInteger());
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.ERROR);
    assertThat(result.phase()).isEqualTo(ScanIssue.ScanPhase.INDEX_WRITE);
    assertThat(result.message()).contains("synthetic-index-failure");
    assertThat(sequence.closes).isEqualTo(1);
  }

  @Test
  void closeFailureCannotReportCandidateSuccess() throws Exception {
    var sequence = new OwnedRecords();
    sequence.failClose = true;
    var result = process(sequence, List.of(), directory, false, new AtomicInteger());
    assertThat(result.outcome()).isEqualTo(FullScanEngine.CandidateOutcome.ERROR);
    assertThat(result.code()).isEqualTo("SOURCE_RESOURCE_CLOSE_FAILED");
    assertThat(result.message()).doesNotContain("synthetic-close-failure");
    assertThat(sequence.closes).isEqualTo(1);
  }

  private FullScanEngine.CandidateResult process(
      OwnedRecords records,
      List<SourceDiagnostic> diagnostics,
      Path output,
      boolean failIndex,
      AtomicInteger writes)
      throws Exception {
    Path file = Files.writeString(directory.resolve("synthetic.jsonl"), "synthetic");
    var fingerprint =
        new SourceFingerprint(
            file.toString(),
            SourceId.CODEX,
            Files.size(file),
            1,
            Optional.empty(),
            Optional.empty());
    var candidate = new Candidate(fingerprint, "codex:synthetic", "synthetic", Map.of());
    var adapter =
        new SourceAdapter() {
          public SourceId sourceId() {
            return SourceId.CODEX;
          }

          public BoundedStream<Candidate> discover(Path root) {
            throw new AssertionError("candidate already selected");
          }

          public SourceFingerprint fingerprint(Path path) {
            return fingerprint;
          }

          public SourceResult parse(Candidate ignored, CancellationSignal cancellation) {
            return SourceResult.Success.managed(diagnostics, 1, records, fingerprint, "synthetic");
          }
        };
    var writer =
        (IndexWriterPort)
            Proxy.newProxyInstance(
                IndexWriterPort.class.getClassLoader(),
                new Class<?>[] {IndexWriterPort.class},
                (proxy, method, args) -> {
                  assertThat(method.getName()).isEqualTo("writeNormalizedContent");
                  assertThat(records.closed).isFalse();
                  var content = (NormalizedSessionContent) args[0];
                  assertThat(Files.readString((Path) args[1]))
                      .contains("session-content.units.v1", "synthetic response");
                  for (int pass = 0; pass < 2; pass++) {
                    long calls = 0;
                    try (var cursor = content.openCursor()) {
                      while (cursor.hasNext()) calls += cursor.next().calls().size();
                    }
                    assertThat(calls).isEqualTo(1);
                  }
                  if (failIndex) throw new IOException("synthetic-index-failure");
                  writes.incrementAndGet();
                  return null;
                });
    return FullScanEngine.processCandidate(
        candidate,
        adapter,
        ScanConfig.defaults(List.of(new ScanConfig.SourceEntry(adapter, directory)), output),
        writer,
        new NormalizationEngine(),
        new NormalizedArtifactWriter());
  }

  /** 测试 owner 持有一个合法小序列，关闭与读取失败均可观察。 */
  private static final class OwnedRecords implements SourceRecordSequence {
    private final SourceRecordSequence delegate =
        SourceRecordSequence.fromList(
            List.of(
                SourceRecord.of("synthetic#event[0]", 0, "assistant")
                    .withContent("synthetic response")));
    private boolean closed;
    private boolean failRead;
    private boolean failClose;
    private int opens;
    private int closes;

    /** 创建独立 owner，测试之间不共享游标位置或关闭状态。 */
    private OwnedRecords() {}

    public long recordCount() {
      return delegate.recordCount();
    }

    public RecordCursor openCursor(long ordinal) throws IOException {
      if (closed) throw new IOException("synthetic-source-closed");
      if (failRead) throw new IOException("synthetic-read-failure");
      opens++;
      return delegate.openCursor(ordinal);
    }

    public void close() throws IOException {
      closes++;
      closed = true;
      delegate.close();
      if (failClose) throw new IOException("synthetic-close-failure");
    }
  }
}
