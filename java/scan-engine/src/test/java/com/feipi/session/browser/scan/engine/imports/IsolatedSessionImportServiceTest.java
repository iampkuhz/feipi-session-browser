package com.feipi.session.browser.scan.engine.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;

/** 独立目录、严格输入、资源额度与生命周期的合成测试。 */
class IsolatedSessionImportServiceTest {
  private static final String TRANSCRIPT =
      "{\"type\":\"assistant\",\"sessionId\":\"shared\",\"message\":{\"content\":\"synthetic\"}}";

  @Test
  void legacyAdapterDefaultMetadataDoesNotReadOrInventEvidence() throws Exception {
    var adapter = new RecordingAdapter();
    assertThat(adapter.singleFileMetadata(Path.of("/synthetic/not-readable.jsonl"))).isEmpty();
    try (var service = new IsolatedSessionImportService(source -> adapter)) {
      var analysis =
          service.create(input(TRANSCRIPT), "synthetic-default.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(analysis.sessionRow().totalTokens()).isEqualTo(10);
      assertThat(analysis.sessionRow().tokenProvenance()).isEqualTo(TokenProvenance.unknown());
    }
  }

  @Test
  void singleFileMetadataIsPassedToParserAndArtifactWithoutDiscoveringNeighbors() throws Exception {
    var metadataFiles = new ArrayList<Path>();
    var metadata =
        Map.of(
            "freshInputTokenPrecision",
            "provider_reported",
            "cacheReadTokenPrecision",
            "provider_reported",
            "cacheWriteTokenPrecision",
            "provider_reported",
            "outputTokenPrecision",
            "provider_reported");
    var adapter =
        new RecordingAdapter() {
          @Override
          public Map<String, String> singleFileMetadata(Path file) throws IOException {
            metadataFiles.add(file);
            try (var entries = Files.list(file.getParent())) {
              assertThat(entries.toList()).containsExactly(file);
            }
            return metadata;
          }

          @Override
          public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
            assertThat(candidate.metadata()).containsAllEntriesOf(metadata);
            return super.parse(candidate, cancellation);
          }
        };
    try (var service = new IsolatedSessionImportService(source -> adapter)) {
      var analysis =
          service.create(
              input(TRANSCRIPT), "synthetic-metadata.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(metadataFiles).hasSize(1);
      assertThat(Files.exists(metadataFiles.getFirst().getParent())).isFalse();
      assertThat(analysis.sessionRow().totalTokens()).isEqualTo(10);
      assertThat(analysis.sessionRow().tokenProvenance())
          .isEqualTo(
              new TokenProvenance(
                  "provider_reported",
                  "provider_reported",
                  "provider_reported",
                  "provider_reported",
                  "",
                  0,
                  0,
                  0));
      assertThat(TokenProvenance.fromMetadata(analysis.artifact().session()))
          .isEqualTo(analysis.sessionRow().tokenProvenance());
    }
  }

  @Test
  void eachUploadUsesPrivateEmptyDirectoryAndCleansItOnSuccessFailureAndClose() throws Exception {
    var adapter = new RecordingAdapter();
    var service = new IsolatedSessionImportService(source -> adapter);
    Path root;
    try (service) {
      var first = service.create(input(TRANSCRIPT), "../same.jsonl", NormalizedAgent.CLAUDE_CODE);
      var second = service.create(input(TRANSCRIPT), "..\\same.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(first.metadata().filename()).isEqualTo("same.jsonl");
      assertThat(first.metadata().importId()).isNotEqualTo(second.metadata().importId());
      assertThat(adapter.files).hasSize(2);
      assertThat(adapter.files.getFirst().getParent())
          .isNotEqualTo(adapter.files.getLast().getParent());
      assertThat(adapter.files).allMatch(path -> !Files.exists(path.getParent()));
      root = adapter.files.getFirst().getParent().getParent();
      assertThat(Files.exists(root)).isTrue();
      adapter.fail = true;
      assertCode(
          () -> service.create(input(TRANSCRIPT), "same.jsonl", NormalizedAgent.CLAUDE_CODE),
          "parse_failed");
      assertThat(adapter.files).allMatch(path -> !Files.exists(path.getParent()));
      assertThat(service.find(first.metadata().importId())).contains(first);
      assertThat(service.delete(first.metadata().importId())).isTrue();
      assertThat(service.delete(first.metadata().importId())).isFalse();
      assertThat(service.find(first.metadata().importId())).isEmpty();
    }
    assertThat(Files.exists(root)).isFalse();
    assertCode(
        () -> service.create(input(TRANSCRIPT), "same.jsonl", NormalizedAgent.CLAUDE_CODE),
        "service_closed");
    service.close();
  }

  @Test
  void invalidInputIsAtomicAndNeverCallsParserOrExposesRawInput() throws Exception {
    var adapter = new RecordingAdapter();
    try (var service = new IsolatedSessionImportService(source -> adapter)) {
      assertCode(
          () -> service.create(input(""), "a.jsonl", NormalizedAgent.CLAUDE_CODE), "empty_input");
      assertCode(
          () -> service.create(input("{secret"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "invalid_jsonl");
      assertCode(
          () -> service.create(input("[]"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "invalid_jsonl");
      assertCode(
          () -> service.create(input("{}{}"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "invalid_jsonl");
      assertCode(
          () ->
              service.create(
                  input("{\"type\":\"unknown\"}"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "unsupported_format");
      assertCode(
          () ->
              service.create(input(TRANSCRIPT + "\n{bad"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "invalid_jsonl");
      assertCode(
          () -> service.create(input(TRANSCRIPT), "a.txt", NormalizedAgent.CLAUDE_CODE),
          "invalid_filename");
      assertCode(
          () ->
              service.create(
                  new ByteArrayInputStream(new byte[] {(byte) 0xc3, 0x28}),
                  "a.jsonl",
                  NormalizedAgent.CLAUDE_CODE),
          "invalid_utf8");
      assertCode(
          () ->
              service.create(
                  input("{\"role\":\"assistant\"}"), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "source_mismatch");
      assertThat(adapter.files).isEmpty();
    }
  }

  @Test
  void byteRecordCharacterAndRetainedSizeLimitsFailWithoutEvictingExistingImport()
      throws Exception {
    assertLimit(new ImportLimits(10, 10, 1000, 2, 100_000), TRANSCRIPT, "file_too_large");
    assertLimit(
        new ImportLimits(1000, 1, 1000, 2, 100_000),
        TRANSCRIPT + "\n" + TRANSCRIPT,
        "too_many_records");
    assertLimit(new ImportLimits(1000, 10, 10, 2, 100_000), TRANSCRIPT, "record_too_large");
    assertLimit(new ImportLimits(1000, 10, 1000, 2, 1), TRANSCRIPT, "analysis_too_large");
    assertLimit(new ImportLimits(1000, 10, 1000, 2, 1000), TRANSCRIPT, "capacity_exceeded");
    try (var service =
        new IsolatedSessionImportService(
            source -> new RecordingAdapter(), new ImportLimits(1000, 10, 1000, 1, 100_000))) {
      var first = service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertCode(
          () -> service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "capacity_exceeded");
      assertThat(service.find(first.metadata().importId())).contains(first);
      service.delete(first.metadata().importId());
      assertThat(
              service
                  .create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE)
                  .metadata()
                  .importId())
          .isNotEqualTo(first.metadata().importId());
    }
  }

  @Test
  void retainedByteQuotaIsAtomicAndDeleteReleasesItsCapacity() throws Exception {
    long size;
    try (var probe = new IsolatedSessionImportService(source -> new RecordingAdapter())) {
      var analysis = probe.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE);
      size = new CanonicalJsonWriter().serialize(analysis.artifact()).length;
    }
    try (var service =
        new IsolatedSessionImportService(
            source -> new RecordingAdapter(), new ImportLimits(1000, 10, 1000, 8, size + 100))) {
      var first = service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertCode(
          () -> service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "capacity_exceeded");
      assertThat(service.find(first.metadata().importId())).contains(first);
      service.delete(first.metadata().importId());
      assertThat(service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE))
          .isNotNull();
    }
  }

  @Test
  void warningDiagnosticsArePreservedSafelyButParserErrorsCannotProducePartialSuccess()
      throws Exception {
    var adapter = new RecordingAdapter();
    try (var service = new IsolatedSessionImportService(source -> adapter)) {
      adapter.diagnostics =
          List.of(
              new SourceDiagnostic(
                  ParseSeverity.WARNING,
                  ParseIssueType.BAD_JSON,
                  "private diagnostic",
                  1,
                  Optional.of("private preview"),
                  "SYNTHETIC_WARNING",
                  "private path",
                  OptionalInt.empty(),
                  OptionalInt.empty(),
                  OptionalInt.empty()));
      var analysis = service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(analysis.artifact().diagnostics())
          .anySatisfy(
              diagnostic -> {
                assertThat(diagnostic.get("code")).isEqualTo("SYNTHETIC_WARNING");
                assertThat(diagnostic.get("message")).isEqualTo("来源诊断：SYNTHETIC_WARNING");
              });
      assertThat(
              new String(
                  new CanonicalJsonWriter().serialize(analysis.artifact()), StandardCharsets.UTF_8))
          .doesNotContain("private diagnostic", "private preview", "private path");
      adapter.diagnostics =
          List.of(
              new SourceDiagnostic(
                  ParseSeverity.ERROR,
                  ParseIssueType.BAD_JSON,
                  "private parse error",
                  1,
                  Optional.empty(),
                  "SYNTHETIC_ERROR",
                  "private path",
                  OptionalInt.empty(),
                  OptionalInt.empty(),
                  OptionalInt.empty()));
      assertCode(
          () -> service.create(input(TRANSCRIPT), "a.jsonl", NormalizedAgent.CLAUDE_CODE),
          "parse_failed");
      assertThat(service.find(analysis.metadata().importId())).contains(analysis);
    }
  }

  @Test
  void concurrentSameFilenameAndSourceIdHaveDifferentStorageAndCacheIdentity() throws Exception {
    var adapter = new RecordingAdapter();
    try (var service = new IsolatedSessionImportService(source -> adapter);
        var executor = Executors.newFixedThreadPool(4)) {
      List<Callable<String>> tasks = new ArrayList<>();
      for (int i = 0; i < 4; i++) {
        tasks.add(
            () ->
                service
                    .create(input(TRANSCRIPT), "same.jsonl", NormalizedAgent.CLAUDE_CODE)
                    .metadata()
                    .importId());
      }
      var results = executor.invokeAll(tasks);
      List<String> ids = new ArrayList<>();
      for (var future : results) {
        ids.add(future.get());
      }
      assertThat(ids).doesNotHaveDuplicates();
      assertThat(ids)
          .allSatisfy(
              id ->
                  assertThat(service.find(id).orElseThrow().sessionRow().sessionKey())
                      .isEqualTo("import:" + id));
      assertThat(adapter.files).hasSize(4).doesNotHaveDuplicates();
    }
  }

  private static void assertLimit(ImportLimits limits, String text, String code) throws Exception {
    try (var service = new IsolatedSessionImportService(source -> new RecordingAdapter(), limits)) {
      assertCode(() -> service.create(input(text), "a.jsonl", NormalizedAgent.CLAUDE_CODE), code);
    }
  }

  private static void assertCode(ThrowingAction action, String code) {
    assertThatThrownBy(action::run)
        .isInstanceOf(SessionImportException.class)
        .hasMessage("独立 JSONL 分析失败（" + code + "）")
        .extracting("code")
        .isEqualTo(code);
  }

  private static ByteArrayInputStream input(String text) {
    return new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8));
  }

  /** 可抛出检查异常的失败断言输入。 */
  private interface ThrowingAction {
    void run() throws Exception;
  }

  /** 记录解析目录且禁止扫描其他文件的合成来源。 */
  private static class RecordingAdapter implements SourceAdapter {
    private final List<Path> files = new ArrayList<>();
    private boolean fail;
    private List<SourceDiagnostic> diagnostics = List.of();

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path path) {
      throw new AssertionError("不得执行来源发现");
    }

    @Override
    public SourceFingerprint fingerprint(Path file) {
      return new SourceFingerprint(
          file.toString(), sourceId(), 1, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      Path file = Path.of(candidate.fingerprint().locator());
      files.add(file);
      try (var siblings = Files.list(file.getParent())) {
        assertThat(siblings.toList()).containsExactly(file);
      } catch (IOException exception) {
        throw new AssertionError(exception);
      }
      if (fail) {
        throw new IllegalArgumentException("private contents " + file);
      }
      var record =
          new SourceRecord(
              file + "#event[0]",
              0,
              "assistant",
              Optional.of("call-1"),
              Optional.of("synthetic-model"),
              Optional.empty(),
              Optional.empty(),
              new SourceRecordUsage(1, 2, 3, 4),
              List.of(),
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              SourceRecordRelation.empty(),
              TRANSCRIPT);
      return new SourceResult.Success(
          diagnostics, 1, List.of(record), candidate.fingerprint(), file.toString());
    }
  }
}
