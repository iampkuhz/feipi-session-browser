package com.feipi.session.browser.scan.engine.imports;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedDiagnostic;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.ImportedSessionAnalysis;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.index.api.imports.SessionImportPort;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;

/**
 * 单文件临时分析服务，不接收个人索引写端口，也不执行来源发现。
 *
 * <p>创建请求串行执行，限制同时解析的内存峰值；每次解析拥有独立目录，成功后立即删除原始上传。 保留的不可变分析按数量及规范 JSON 大小限额管理，删除或关闭时释放。
 */
public final class IsolatedSessionImportService implements SessionImportPort {
  private final Function<NormalizedAgent, SourceAdapter> adapters;
  private final ImportLimits limits;
  private final Path root;
  private final Map<String, StoredImport> imports = new LinkedHashMap<>();
  private long storedBytes;
  private boolean closed;

  /** 使用默认资源策略与外部注入的真实来源解析器。 */
  public IsolatedSessionImportService(Function<NormalizedAgent, SourceAdapter> adapters)
      throws IOException {
    this(adapters, ImportLimits.defaults());
  }

  /** 使用显式资源策略；不读取任何用户配置或会话目录。 */
  public IsolatedSessionImportService(
      Function<NormalizedAgent, SourceAdapter> adapters, ImportLimits limits) throws IOException {
    this.adapters = Objects.requireNonNull(adapters, "adapters");
    this.limits = Objects.requireNonNull(limits, "limits");
    root = privateDirectory(null);
  }

  @Override
  public synchronized ImportedSessionAnalysis create(
      InputStream input, String filename, NormalizedAgent source) throws IOException {
    Objects.requireNonNull(input, "input");
    Objects.requireNonNull(source, "source");
    if (closed) {
      throw ImportInputValidator.failure("service_closed");
    }
    String displayName = displayName(filename);
    if (imports.size() >= limits.maxImports()) {
      throw ImportInputValidator.failure("capacity_exceeded");
    }
    String id = UUID.randomUUID().toString();
    Path workspace = privateDirectory(root);
    try {
      Path file = workspace.resolve("upload.jsonl");
      long size = copy(input, file);
      String originalId = ImportInputValidator.validate(file, source, limits);
      NormalizedSessionArtifact artifact = analyze(file, id, source);
      long encodedSize = new CanonicalJsonWriter().serializedSize(artifact);
      if (encodedSize > limits.maxStoredBytes() - storedBytes) {
        throw ImportInputValidator.failure("capacity_exceeded");
      }
      var metadata =
          new ImportedSessionMetadata(id, source, displayName, originalId, size, Instant.now());
      var result =
          new ImportedSessionAnalysis(
              metadata, new ImportedSessionRecord(metadata, artifact), artifact);
      // 原始文件清理完成才提交结果，失败不会污染已有分析。
      clean(workspace);
      imports.put(id, new StoredImport(result, encodedSize));
      storedBytes += encodedSize;
      return result;
    } catch (SessionImportException exception) {
      throw exception;
    } catch (IOException | RuntimeException exception) {
      throw ImportInputValidator.failure("parse_failed", exception);
    } finally {
      clean(workspace);
    }
  }

  private NormalizedSessionArtifact analyze(Path file, String id, NormalizedAgent source)
      throws IOException {
    SourceAdapter adapter = adapters.apply(source);
    if (adapter == null || !adapter.sourceId().getValue().equals(source.getValue())) {
      throw ImportInputValidator.failure("source_mismatch");
    }
    Map<String, String> metadata = adapter.singleFileMetadata(file);
    var candidate = new Candidate(adapter.fingerprint(file), "import:" + id, "", metadata);
    SourceResult result = adapter.parse(candidate, null);
    if (!(result instanceof SourceResult.Success success)) {
      throw ImportInputValidator.failure("parse_failed");
    }
    try (success) {
      if (success.diagnostics().stream()
          .anyMatch(diagnostic -> diagnostic.severity() == ParseSeverity.ERROR)) {
        throw ImportInputValidator.failure("parse_failed");
      }
      String logicalPath = "imports/" + id + "/upload.jsonl";
      var sequence = success.recordSequence();
      long count = 0;
      long contentChars = 0;
      boolean hasUser = false;
      try (var cursor = sequence.openCursor()) {
        while (cursor.hasNext()) {
          var record = cursor.next();
          count++;
          contentChars = Math.addExact(contentChars, record.content().length());
          hasUser |= "user".equals(record.eventType());
        }
      }
      if (count != sequence.recordCount()) throw new IOException("Source record count mismatch");
      // 内容规模先受保留制品剩余额度约束，避免在规范化前构造超出服务预算的载荷。
      if (contentChars > limits.maxStoredBytes() - storedBytes) {
        throw ImportInputValidator.failure("analysis_too_large");
      }
      // 保持原导入容量：只有通过原最坏体积策略后才物化并替换为逻辑路径。
      List<SourceRecord> records = new ArrayList<>();
      try (var cursor = sequence.openCursor()) {
        while (cursor.hasNext()) records.add(relocate(cursor.next(), logicalPath));
      }
      if (records.size() != count) throw new IOException("Source replay count mismatch");
      List<SourceDiagnostic> diagnostics =
          success.diagnostics().stream()
              .map(
                  diagnostic ->
                      new SourceDiagnostic(
                          diagnostic.severity(),
                          diagnostic.issueType(),
                          "来源诊断：" + diagnostic.code(),
                          diagnostic.lineNo(),
                          Optional.empty(),
                          diagnostic.code(),
                          logicalPath,
                          diagnostic.column(),
                          diagnostic.byteRangeStart(),
                          diagnostic.byteRangeEnd()))
              .toList();
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT,
                  Path.of(logicalPath),
                  Optional.empty(),
                  Optional.empty()));
      NormalizedSessionArtifact artifact =
          new NormalizationEngine().normalize(source, records, diagnostics, files);
      if (artifact.calls().isEmpty() && !hasUser) {
        throw ImportInputValidator.failure("empty_input");
      }
      var allDiagnostics = new ArrayList<>(artifact.diagnostics());
      allDiagnostics.add(
          new NormalizedDiagnostic(
              Map.of(
                  "severity",
                  "info",
                  "code",
                  "SINGLE_FILE_ONLY",
                  "message",
                  "仅分析上传的单个文件；未读取本机邻居、子会话或 sidecar，外部上下文可能缺失。")));
      var catalog = ImportPayloadCatalog.read(file, logicalPath);
      Map<String, Object> session = new LinkedHashMap<>(artifact.session());
      applySingleFileMetadata(session, metadata);
      return new NormalizedSessionArtifact(
          artifact.schemaVersion(),
          artifact.agent(),
          artifact.sourceFiles(),
          session,
          ImportToolDeclarations.restore(artifact.calls(), artifact.toolExecutions(), catalog),
          artifact.toolExecutions(),
          allDiagnostics,
          catalog,
          artifact.sourceUnitSequences());
    }
  }

  private static SourceRecord relocate(SourceRecord record, String logicalPath) {
    return new SourceRecord(
        logicalPath + "#event[" + record.eventIndex() + "]",
        record.eventIndex(),
        record.eventType(),
        record.callId(),
        record.model(),
        record.timestamp(),
        record.turnId(),
        record.usage(),
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        record.relation(),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing(),
        record.metaContext(),
        record.messageRole());
  }

  /** 来源精度独立于数值；只覆盖显式估算段，正式 usage 保持解析器原值。 */
  private static void applySingleFileMetadata(
      Map<String, Object> session, Map<String, String> metadata) {
    session.putAll(TokenProvenance.fromMetadata(metadata).toMetadata());
    Map<String, String> precisionKeys =
        Map.of(
            "freshInputTokens",
            "freshInputTokenPrecision",
            "cacheReadTokens",
            "cacheReadTokenPrecision",
            "cacheWriteTokens",
            "cacheWriteTokenPrecision",
            "outputTokens",
            "outputTokenPrecision");
    boolean estimated = false;
    for (var entry : precisionKeys.entrySet()) {
      if ("estimated".equals(metadata.get(entry.getValue()))
          && metadata.containsKey(entry.getKey())) {
        long value = Long.parseLong(metadata.get(entry.getKey()));
        if (value < 0) {
          throw new IllegalArgumentException("Single-file token estimate must be nonnegative");
        }
        session.put(entry.getKey(), value);
        estimated = true;
      }
    }
    if (estimated) {
      long total =
          precisionKeys.keySet().stream()
              .map(session::get)
              .filter(Number.class::isInstance)
              .map(Number.class::cast)
              .mapToLong(Number::longValue)
              .sum();
      session.put("totalTokens", total);
    }
  }

  private long copy(InputStream input, Path target) throws IOException {
    long size = 0;
    byte[] buffer = new byte[8192];
    try (var output = Files.newOutputStream(target)) {
      int read;
      while ((read = input.read(buffer)) != -1) {
        if (read > limits.maxFileBytes() - size) {
          throw ImportInputValidator.failure("file_too_large");
        }
        output.write(buffer, 0, read);
        size += read;
      }
    }
    return size;
  }

  private static String displayName(String filename) throws IOException {
    if (filename == null) {
      throw ImportInputValidator.failure("invalid_filename");
    }
    String name = filename.replace('\\', '/');
    name = name.substring(name.lastIndexOf('/') + 1).replaceAll("[\\p{Cntrl}]", "");
    if (name.length() > 255 || !name.toLowerCase(Locale.ROOT).endsWith(".jsonl")) {
      throw ImportInputValidator.failure("invalid_filename");
    }
    return name;
  }

  private static Path privateDirectory(Path parent) throws IOException {
    try {
      var permissions =
          PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------"));
      return parent == null
          ? Files.createTempDirectory("feipi-import-", permissions)
          : Files.createTempDirectory(parent, "upload-", permissions);
    } catch (UnsupportedOperationException exception) {
      return parent == null
          ? Files.createTempDirectory("feipi-import-")
          : Files.createTempDirectory(parent, "upload-");
    }
  }

  private static void deleteTree(Path directory) throws IOException {
    if (!Files.exists(directory)) {
      return;
    }
    try (var paths = Files.walk(directory)) {
      for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
        Files.deleteIfExists(path);
      }
    }
  }

  private static void clean(Path directory) throws IOException {
    try {
      deleteTree(directory);
    } catch (IOException exception) {
      throw ImportInputValidator.failure("cleanup_failed", exception);
    }
  }

  @Override
  public synchronized Optional<ImportedSessionAnalysis> find(String importId) {
    StoredImport stored = imports.get(importId);
    return stored == null ? Optional.empty() : Optional.of(stored.analysis());
  }

  @Override
  public synchronized boolean delete(String importId) {
    StoredImport removed = imports.remove(importId);
    if (removed == null) {
      return false;
    }
    storedBytes -= removed.encodedSize();
    return true;
  }

  @Override
  public ImportLimits limits() {
    return limits;
  }

  @Override
  public synchronized void close() throws IOException {
    closed = true;
    imports.clear();
    storedBytes = 0;
    clean(root);
  }

  /**
   * 单份不可变分析与计入资源配额的大小。
   *
   * @param analysis 独立导入的不可变分析结果
   * @param encodedSize 计入保留资源配额的规范 JSON 字节数
   */
  private record StoredImport(ImportedSessionAnalysis analysis, long encodedSize) {}
}
