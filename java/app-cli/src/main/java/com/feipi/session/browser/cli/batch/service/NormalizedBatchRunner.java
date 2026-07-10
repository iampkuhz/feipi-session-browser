package com.feipi.session.browser.cli.batch.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.cli.batch.protocol.NormalizationResultRecord;
import com.feipi.session.browser.cli.batch.protocol.NormalizedBatchProtocol;
import com.feipi.session.browser.cli.batch.protocol.SourceRootRequestRecord;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.NormalizedArtifactWriter;
import com.feipi.session.browser.scan.artifact.WriteResult;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprintMaps;
import com.feipi.session.browser.source.spi.SourceNormalizationInputs;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * normalized batch 协议执行器。
 *
 * <p>本类承载 stdin NDJSON 解析、源根处理、归一化、制品写入和 stdout NDJSON 输出。CLI 只负责参数解析和提供 {@link
 * SourceAdapterResolver}。
 */
public final class NormalizedBatchRunner {

  private final ObjectMapper mapper;
  private final NormalizationEngine engine;
  private final NormalizedArtifactWriter writer;

  private Path outputDir;
  private PrintStream output;
  private boolean headerEmitted;
  private int requestCount;

  /** 创建默认 batch runner。 */
  public NormalizedBatchRunner() {
    this.mapper = new ObjectMapper();
    this.engine = new NormalizationEngine();
    this.writer = new NormalizedArtifactWriter();
  }

  /**
   * 执行批量归一化流程。
   *
   * @param input NDJSON 输入流
   * @param output NDJSON 输出流
   * @param outputDir 归一化制品输出目录
   * @param resolver sourceId 到源适配器的解析器
   * @return 退出码：0 表示正常完成，1 表示协议级错误
   * @throws Exception 初始化或目录创建失败时抛出异常
   */
  public int run(
      InputStream input, PrintStream output, Path outputDir, SourceAdapterResolver resolver)
      throws Exception {
    this.outputDir = outputDir;
    this.output = output;
    this.headerEmitted = false;
    this.requestCount = 0;

    Files.createDirectories(outputDir);

    boolean protocolBroken = false;
    try (BufferedReader reader =
        new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        line = line.strip();
        if (line.isEmpty()) {
          continue;
        }
        try {
          processInputLine(line, resolver);
        } catch (Exception e) {
          protocolBroken = true;
          break;
        }
      }
    }

    if (headerEmitted) {
      Map<String, Object> end = new LinkedHashMap<>();
      end.put(NormalizedBatchProtocol.FIELD_TYPE, NormalizedBatchProtocol.TYPE_END);
      end.put(NormalizedBatchProtocol.FIELD_TOTAL_REQUESTS, requestCount);
      emitProtocolLine(end);
    }

    output.flush();
    return protocolBroken ? 1 : 0;
  }

  private void processInputLine(String line, SourceAdapterResolver resolver) {
    SourceRootRequestRecord input;
    String requestId;
    try {
      input = mapper.readValue(line, SourceRootRequestRecord.class);
      requestId = input.requestId();
      if (requestId == null || requestId.isBlank()) {
        requestId = generateRequestId();
      }
    } catch (Exception e) {
      requestId = generateRequestId();
      ensureHeader();
      emitRequest(requestId, null, null);
      emitResult(
          new NormalizationResultRecord(
              requestId,
              "",
              NormalizedBatchProtocol.STATUS_ERROR,
              null,
              "Invalid input JSON",
              null));
      return;
    }

    if (input.sourceId() == null || input.rootPath() == null) {
      ensureHeader();
      emitRequest(requestId, input.sourceId(), input.rootPath());
      emitResult(
          new NormalizationResultRecord(
              requestId,
              "",
              NormalizedBatchProtocol.STATUS_ERROR,
              null,
              "Missing sourceId or rootPath in input",
              null));
      return;
    }

    ensureHeader();
    emitRequest(requestId, input.sourceId(), input.rootPath());
    requestCount++;

    try {
      SourceAdapter adapter = resolver.forSourceId(input.sourceId());
      Path rootPath = Path.of(input.rootPath());
      processRootInput(adapter, rootPath, requestId);
    } catch (IllegalArgumentException e) {
      emitResult(
          new NormalizationResultRecord(
              requestId, "", NormalizedBatchProtocol.STATUS_ERROR, null, sanitizeError(e), null));
    } catch (Exception e) {
      emitResult(
          new NormalizationResultRecord(
              requestId, "", NormalizedBatchProtocol.STATUS_ERROR, null, sanitizeError(e), null));
    }
  }

  private void processRootInput(SourceAdapter adapter, Path rootPath, String requestId) {
    SourceRoot root = adapter.checkRoot(rootPath);
    if (!root.isSafe()) {
      emitResult(
          new NormalizationResultRecord(
              requestId, "", NormalizedBatchProtocol.STATUS_ERROR, null, "Unsafe root path", null));
      return;
    }

    var candidates = adapter.discover(rootPath);
    for (Candidate candidate : candidates.orderedItems()) {
      processCandidate(candidate, adapter, requestId);
    }
  }

  private void processCandidate(Candidate candidate, SourceAdapter adapter, String requestId) {
    String sessionKey = candidate.sessionKey();
    try {
      SourceResult parseResult = adapter.parse(candidate, null);

      if (parseResult instanceof SourceResult.Skipped skipped) {
        emitResult(
            new NormalizationResultRecord(
                requestId,
                sessionKey,
                NormalizedBatchProtocol.STATUS_SKIPPED,
                null,
                sanitizeError(skipped.reason()),
                null));
        return;
      }
      if (parseResult instanceof SourceResult.Fatal fatal) {
        emitResult(
            new NormalizationResultRecord(
                requestId,
                sessionKey,
                NormalizedBatchProtocol.STATUS_ERROR,
                null,
                sanitizeError(fatal.errorDetail()),
                null));
        return;
      }
      if (parseResult instanceof SourceResult.RetryableIncomplete retryable) {
        emitResult(
            new NormalizationResultRecord(
                requestId,
                sessionKey,
                NormalizedBatchProtocol.STATUS_ERROR,
                null,
                sanitizeError(retryable.reason()),
                null));
        return;
      }

      if (!(parseResult instanceof SourceResult.Success success)) {
        emitResult(
            new NormalizationResultRecord(
                requestId,
                sessionKey,
                NormalizedBatchProtocol.STATUS_ERROR,
                null,
                "Unknown parse status",
                null));
        return;
      }

      List<SourceDiagnostic> diagnostics = success.diagnostics();
      Path filePath = SourceNormalizationInputs.transcriptPath(candidate);
      NormalizedSessionArtifact artifact =
          engine.normalize(
              SourceNormalizationInputs.normalizedAgent(adapter),
              success.records(),
              diagnostics,
              SourceNormalizationInputs.transcriptFiles(candidate));
      Map<String, String> fingerprints = SourceFingerprintMaps.forCandidate(filePath, candidate);
      WriteResult writeResult = writer.write(outputDir, artifact, fingerprints);

      emitResult(
          new NormalizationResultRecord(
              requestId,
              sessionKey,
              NormalizedBatchProtocol.STATUS_SUCCESS,
              writeResult.dataPath().toString(),
              null,
              writeResult.contentHash()));
    } catch (Exception e) {
      emitResult(
          new NormalizationResultRecord(
              requestId,
              sessionKey,
              NormalizedBatchProtocol.STATUS_ERROR,
              null,
              sanitizeError(e),
              null));
    }
  }

  private void ensureHeader() {
    if (!headerEmitted) {
      Map<String, Object> header = new LinkedHashMap<>();
      header.put(NormalizedBatchProtocol.FIELD_PROTOCOL, NormalizedBatchProtocol.PROTOCOL_NAME);
      header.put(NormalizedBatchProtocol.FIELD_VERSION, NormalizedBatchProtocol.PROTOCOL_VERSION);
      emitProtocolLine(header);
      headerEmitted = true;
    }
  }

  private void emitRequest(String requestId, String sourceId, String rootPath) {
    Map<String, Object> req = new LinkedHashMap<>();
    req.put(NormalizedBatchProtocol.FIELD_TYPE, NormalizedBatchProtocol.TYPE_REQUEST);
    req.put(NormalizedBatchProtocol.FIELD_REQUEST_ID, requestId);
    if (sourceId != null) {
      req.put(NormalizedBatchProtocol.FIELD_SOURCE_ID, sourceId);
    }
    if (rootPath != null) {
      req.put(NormalizedBatchProtocol.FIELD_ROOT_PATH, rootPath);
    }
    emitProtocolLine(req);
  }

  private void emitResult(NormalizationResultRecord record) {
    try {
      output.println(mapper.writeValueAsString(record));
    } catch (Exception e) {
      throw new IllegalStateException("Output serialization failed", e);
    }
  }

  private void emitProtocolLine(Object data) {
    try {
      output.println(mapper.writeValueAsString(data));
    } catch (Exception e) {
      throw new IllegalStateException("Protocol serialization failed", e);
    }
  }

  private static String generateRequestId() {
    return "req-" + UUID.randomUUID();
  }

  private static String sanitizeError(Exception e) {
    return sanitizeError(e.getMessage());
  }

  private static String sanitizeError(String message) {
    if (message == null || message.isBlank()) {
      return "Processing error";
    }
    String sanitized = message.replaceAll("/[^\\s:'\"]+", "$0");
    return sanitized.replaceAll("(/[^/\\s:'\"]+/)+([^/\\s:'\"]+)", "$2");
  }
}
