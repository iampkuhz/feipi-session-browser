package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.index.api.write.IndexWriterPort;
import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.NormalizedArtifactWriter;
import com.feipi.session.browser.scan.artifact.WriteResult;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprintMaps;
import com.feipi.session.browser.source.spi.SourceNormalizationInputs;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Java full scan 引擎。
 *
 * <p>实现完整的全量扫描 use case：session 发现、candidate 分类、artifact 生产和 index 写入。
 *
 * <p>处理管线：
 *
 * <ol>
 *   <li>确保 index schema 已就绪。
 *   <li>写入 {@code scan_log} 行（{@code status = 'running'}）。
 *   <li>遍历每个源条目：安全检查 → 发现候选项 → 逐候选解析 → 归一化 → 写入制品 → 提交 index 写入端口。
 *   <li>通过 {@link IndexWriterPort} 批量提交 index 行。
 *   <li>更新 {@code scan_log} 行（{@code success} 或 {@code failure}）。
 *   <li>返回 {@link ScanSummary}。
 * </ol>
 *
 * <p>复用现有组件：
 *
 * <ul>
 *   <li>{@link NormalizationEngine} — 纯函数归一化
 *   <li>{@link NormalizedArtifactWriter} — 失败安全制品写入
 *   <li>{@link IndexWriterPort} — index 写入与 scan log 抽象端口
 * </ul>
 *
 * <p>校验放置：根目录安全检查在 {@link SourceAdapter#checkRoot} 边界执行一次； 归一化制品信任 domain 不变量已验证， index
 * 约束由写入端口实现负责。
 */
public final class FullScanEngine {

  private static final Logger log = LoggerFactory.getLogger(FullScanEngine.class);

  /** 每 N 个候选项 flush 一次 index writer，限制待写队列内存。 */
  private static final int FLUSH_INTERVAL = 100;

  private final NormalizationEngine normalizationEngine;
  private final NormalizedArtifactWriter artifactWriter;

  /**
   * 使用默认归一化引擎和制品写入器创建 full scan 引擎。
   *
   * <p>归一化引擎和制品写入器在 scan 生命周期内各创建一次， 不对每个候选项重建。
   */
  public FullScanEngine() {
    this(new NormalizationEngine(), new NormalizedArtifactWriter());
  }

  /**
   * 使用指定的归一化引擎和制品写入器创建 full scan 引擎。
   *
   * <p>用于测试注入。
   *
   * @param normalizationEngine 归一化引擎
   * @param artifactWriter 制品写入器
   */
  public FullScanEngine(
      NormalizationEngine normalizationEngine, NormalizedArtifactWriter artifactWriter) {
    this.normalizationEngine =
        Objects.requireNonNull(normalizationEngine, "normalizationEngine 不得为 null");
    this.artifactWriter = Objects.requireNonNull(artifactWriter, "artifactWriter 不得为 null");
  }

  /**
   * 执行全量扫描（无进度回调）。
   *
   * @param indexWriter index 写入端口，由调用方创建和管理生命周期
   * @param config 扫描配置
   * @return 扫描汇总结果
   * @throws NullPointerException 当参数为 null 时
   */
  public ScanSummary scan(IndexWriterPort indexWriter, ScanConfig config) {
    return scan(indexWriter, config, null);
  }

  /**
   * 执行全量扫描，支持进度回调。
   *
   * <p>通过写入端口串行完成全部操作：schema 确保 → scan_log 开始 → 逐源处理 → index 写入 → scan_log 完成。 原始 source
   * 文件只读，不做任何修改。
   *
   * @param indexWriter index 写入端口，由调用方创建和管理生命周期
   * @param config 扫描配置
   * @param progress 可选的进度回调，null 表示不报告进度
   * @return 扫描汇总结果
   * @throws NullPointerException 当 indexWriter 或 config 为 null 时
   */
  public ScanSummary scan(IndexWriterPort indexWriter, ScanConfig config, ScanProgress progress) {
    var fatal = new ScanFatalDiagnostics("full");
    try {
      return scan(indexWriter, config, progress, fatal);
    } catch (Error error) {
      fatal.report(error);
      throw error;
    }
  }

  private ScanSummary scan(
      IndexWriterPort indexWriter,
      ScanConfig config,
      ScanProgress progress,
      ScanFatalDiagnostics fatal) {
    Objects.requireNonNull(indexWriter, "indexWriter 不得为 null");
    Objects.requireNonNull(config, "config 不得为 null");

    long startMs = System.currentTimeMillis();
    double startEpoch = startMs / 1000.0;

    // 每次扫描使用不可变制品代，失败不得覆盖上一已发布代。
    config =
        new ScanConfig(
            config.sourceEntries(),
            config.artifactOutputDir().resolve(UUID.randomUUID().toString()),
            config.agentFilter(),
            config.parseParallelism());

    // 确保 artifact 输出目录存在
    try {
      Files.createDirectories(config.artifactOutputDir().getParent());
    } catch (IOException e) {
      return buildErrorSummary(
          startMs,
          fatal.setupFailure(
              ScanIssue.ScanPhase.ARTIFACT_WRITE, "SCAN_ARTIFACT_DIRECTORY_FAILED", e),
          fatal.scanLogId());
    }

    fatal.at("SCHEMA_INIT", "");
    // 1. 确保 schema
    try {
      long phaseStart = System.nanoTime();
      if (progress != null) progress.onPhaseStart("schema");
      indexWriter.ensureSchema();
      if (progress != null)
        progress.onPhaseEnd("schema", (System.nanoTime() - phaseStart) / 1_000_000);
    } catch (RuntimeException e) {
      return buildErrorSummary(
          startMs,
          fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_SCHEMA_INIT_FAILED", e),
          fatal.scanLogId());
    }

    fatal.at("SCAN_LOG_START", "");
    // 2. 开始 scan_log
    long scanLogId;
    try {
      scanLogId = indexWriter.startScan(startEpoch);
    } catch (RuntimeException e) {
      return buildErrorSummary(
          startMs,
          fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_LOG_START_FAILED", e),
          fatal.scanLogId());
    }

    fatal.scanStarted(scanLogId);
    boolean scanLogFinalized = false;
    fatal.at("INDEX_PREPARE", "");
    try {
      // 1b. 重建所选来源；无过滤时才重建完整索引，保留未扫描来源。
      try {
        long phaseStart = System.nanoTime();
        if (progress != null) progress.onPhaseStart("clear_index");
        indexWriter.clearExistingIndex(config.agentFilter());
        if (progress != null)
          progress.onPhaseEnd("clear_index", (System.nanoTime() - phaseStart) / 1_000_000);
      } catch (RuntimeException e) {
        return buildErrorSummary(
            startMs,
            fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_INDEX_PREPARE_FAILED", e),
            fatal.scanLogId());
      }

      // 3. 处理各源
      List<ScanIssue> issues = new ArrayList<>();
      Map<com.feipi.session.browser.source.spi.SourceId, Integer> perSourceCount =
          new LinkedHashMap<>();
      Map<String, Integer> perSourceCountByValue = new LinkedHashMap<>();
      int[] counters = new int[3]; // 计数器数组：候选总数、成功数、错误与跳过数
      int skippedCount = 0;

      boolean scanFailed = false;

      for (ScanConfig.SourceEntry entry : config.sourceEntries()) {
        String agentValue = entry.adapter().sourceId().getValue();

        // agent 过滤
        if (!config.isAgentAllowed(agentValue)) {
          log.info("跳过被过滤的源: {}", agentValue);
          continue;
        }

        fatal.at("ROOT_CHECK", agentValue);
        // 根目录安全检查
        SourceRoot root = entry.adapter().checkRoot(entry.rootPath());
        if (!root.isSafe()) {
          issues.add(
              new ScanIssue(
                  "",
                  agentValue,
                  ScanIssue.ScanPhase.ROOT_CHECK,
                  "Unsafe root: " + entry.rootPath()));
          continue;
        }

        // 空根目录检查
        if (!Files.isDirectory(entry.rootPath())) {
          log.info("源根目录不存在或不是目录: {}", agentValue);
          continue;
        }

        fatal.at("DISCOVERY", agentValue);
        // 发现候选项
        BoundedStream<Candidate> candidates;
        try {
          String discoverPhase = "discover:" + agentValue;
          long phaseStart = System.nanoTime();
          if (progress != null) progress.onPhaseStart(discoverPhase);
          candidates = entry.adapter().discover(entry.rootPath());
          if (progress != null)
            progress.onPhaseEnd(discoverPhase, (System.nanoTime() - phaseStart) / 1_000_000);
        } catch (Exception e) {
          issues.add(new ScanIssue("", agentValue, ScanIssue.ScanPhase.DISCOVERY, e.getMessage()));
          continue;
        }

        int sourceCount = candidates.size();
        counters[0] += sourceCount;

        if (progress != null) {
          progress.onSourceStart(agentValue, sourceCount);
        }

        fatal.at("CANDIDATE", agentValue);
        // 逐候选处理
        int processedInBatch = 0;
        int progressCount = 0;
        int sourceSuccessCount = 0;
        for (Candidate candidate : candidates.orderedItems()) {
          CandidateResult result;

          // 零值指纹 → transcript/rollout 缺失 → 创建最小 index entry
          if (isTranscriptMissing(candidate)) {
            result = processTranscriptMissingCandidate(candidate, entry.adapter(), indexWriter);
          } else {
            result =
                processCandidate(
                    candidate,
                    entry.adapter(),
                    config,
                    indexWriter,
                    normalizationEngine,
                    artifactWriter);
          }

          switch (result.outcome) {
            case SUCCESS -> {
              counters[1]++;
              sourceSuccessCount++;
              perSourceCount.merge(entry.adapter().sourceId(), 1, Integer::sum);
              perSourceCountByValue.merge(agentValue, 1, Integer::sum);
            }
            case SKIPPED -> skippedCount++;
            case ERROR -> {
              counters[2]++;
              issues.add(result.issue(candidate.sessionKey(), agentValue));
            }
            default -> {}
          }
          processedInBatch++;
          progressCount++;

          if (progress != null) {
            progress.onCandidateProcessed(agentValue, progressCount, sourceCount);
          }

          // 定期 flush
          if (processedInBatch >= FLUSH_INTERVAL && indexWriter.pendingWriteCount() > 0) {
            fatal.at("INDEX_FLUSH", agentValue);
            if (!ScanFlush.flush(indexWriter, progress, "flush", agentValue, issues)) {
              scanFailed = true;
            }
            fatal.at("CANDIDATE", agentValue);
            processedInBatch = 0;
          }
        }

        if (progress != null) {
          progress.onSourceEnd(agentValue, sourceSuccessCount);
        }
      }

      // 4. 最终 flush
      fatal.at("INDEX_FLUSH", "");
      if (!scanFailed && indexWriter.pendingWriteCount() > 0) {
        if (!ScanFlush.flush(indexWriter, progress, "flush_final", "", issues)) {
          scanFailed = true;
        }
      }

      scanFailed = scanFailed || !issues.isEmpty() || counters[2] > 0;

      // 5. 完成 scan_log
      fatal.at("SCAN_LOG_FINISH", "");
      long endMs = System.currentTimeMillis();
      double endEpoch = endMs / 1000.0;
      try {
        if (scanFailed) {
          indexWriter.failScan(
              scanLogId,
              endEpoch,
              perSourceCountByValue,
              Math.max(counters[2], issues.size()),
              ScanDiagnostics.failures(issues));
        } else {
          if (config.agentFilter().isEmpty()) {
            indexWriter.saveScanLogicVersion(
                IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION, Instant.ofEpochMilli(endMs));
          }
          indexWriter.completeScan(scanLogId, endEpoch, perSourceCountByValue);
        }
        scanLogFinalized = true;
      } catch (RuntimeException e) {
        issues.add(
            fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_LOG_FINISH_FAILED", e));
      }

      long duration = endMs - startMs;
      return new ScanSummary(
          counters[0],
          counters[1],
          skippedCount,
          Math.max(counters[2], issues.size()),
          duration,
          scanLogId,
          perSourceCount,
          issues);
    } catch (Error error) {
      fatal.report(error);
      throw error;
    } finally {
      if (!scanLogFinalized) {
        try {
          indexWriter.failScan(
              scanLogId, System.currentTimeMillis() / 1000.0, Map.of(), fatal.failures());
        } catch (RuntimeException | Error cleanup) {
          if (!fatal.hasReportedJvmError()) throw cleanup;
          log.error("scan_log 最终标记失败: exception={}", cleanup.getClass().getName());
        }
      }
    }
  }

  /**
   * 处理单个候选项：解析 → 归一化 → 写入制品 → 构建 index SQL。
   *
   * <p>成功时将写入请求添加到 index 写入端口。失败时记录问题但不中断整体扫描。
   *
   * @param candidate 待处理候选项
   * @param adapter 源适配器
   * @param config 扫描配置
   * @param indexWriter index 写入端口
   * @param normEngine 归一化引擎
   * @param artWriter 制品写入器
   * @return 候选项处理结果
   */
  static CandidateResult processCandidate(
      Candidate candidate,
      SourceAdapter adapter,
      ScanConfig config,
      IndexWriterPort indexWriter,
      NormalizationEngine normEngine,
      NormalizedArtifactWriter artWriter) {

    try {
      // 1. 解析
      SourceResult parseResult;
      try {
        parseResult = adapter.parse(candidate, null);
      } catch (RuntimeException exception) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, "", "SOURCE_PARSER_EXCEPTION");
      }

      if (parseResult instanceof SourceResult.Skipped skipped) {
        return new CandidateResult(
            CandidateOutcome.SKIPPED, ScanIssue.ScanPhase.PARSE, skipped.reason());
      }
      if (parseResult instanceof SourceResult.Fatal fatal) {
        return parseFailure(fatal.code(), fatal.diagnostics());
      }
      if (parseResult instanceof SourceResult.RetryableIncomplete retryable) {
        return parseFailure("SOURCE_RETRYABLE_INCOMPLETE", retryable.diagnostics());
      }
      if (!(parseResult instanceof SourceResult.Success success)) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, "Unknown parse result type");
      }

      CandidateResult processed = null;
      try (success) {
        processed =
            processParsedCandidate(
                candidate, adapter, config, indexWriter, normEngine, artWriter, success);
      } catch (Exception cleanup) {
        if (processed != null && processed.outcome() == CandidateOutcome.ERROR) {
          return processed;
        }
        return parseFailure("SOURCE_RESOURCE_CLOSE_FAILED", List.of());
      }
      return processed;
    } catch (Exception e) {
      return new CandidateResult(
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.NORMALIZE, exceptionMessage(e));
    }
  }

  private static CandidateResult parseFailure(String code, List<SourceDiagnostic> diagnostics) {
    return new CandidateResult(
        CandidateOutcome.ERROR,
        ScanIssue.ScanPhase.PARSE,
        "SOURCE_ERRORS:" + ScanDiagnostics.sourceErrors(diagnostics),
        code);
  }

  /** 在源 owner 仍有效时完成全部重放；源错误早退及任意阶段失败都由调用层关闭 owner。 */
  private static CandidateResult processParsedCandidate(
      Candidate candidate,
      SourceAdapter adapter,
      ScanConfig config,
      IndexWriterPort indexWriter,
      NormalizationEngine normEngine,
      NormalizedArtifactWriter artWriter,
      SourceResult.Success success) {
    try {
      String sourceErrors = ScanDiagnostics.sourceErrors(success.diagnostics());
      if (!sourceErrors.isEmpty()) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, "SOURCE_ERRORS:" + sourceErrors);
      }

      // 2. 归一化
      Path filePath = SourceNormalizationInputs.transcriptPath(candidate);
      List<SourceDiagnostic> diagnostics = success.diagnostics();
      NormalizedSessionContent content =
          success.hasManagedRecords()
              ? normEngine.normalizeContent(
                  SourceNormalizationInputs.normalizedAgent(adapter),
                  success.recordSequence(),
                  diagnostics,
                  SourceNormalizationInputs.transcriptFiles(candidate))
              : normEngine.normalizeContent(
                  SourceNormalizationInputs.normalizedAgent(adapter),
                  success.records(),
                  diagnostics,
                  SourceNormalizationInputs.transcriptFiles(candidate));

      // 2b. 注入 candidate 元数据到 session map（归一化引擎是纯函数，不含源特定标识）
      String safeSessionKey = candidate.sessionKey().replace('/', ':');
      String sessionId = extractSessionId(safeSessionKey, filePath);
      Map<String, Object> enrichedSession = new LinkedHashMap<>(content.header().session());
      enrichedSession.put("session_key", safeSessionKey);
      enrichedSession.put("session_id", sessionId);
      enrichedSession.put("project_key", candidate.projectKey());
      CandidateContentMetadata.apply(enrichedSession, candidate, adapter, content);
      enrichedSession.put(
          "candidate_metadata_fingerprint", CandidateMetadataFingerprint.from(candidate));
      putStringIfAbsent(enrichedSession, "started_at", candidate.metadata().get("started_at"));
      putStringIfAbsent(enrichedSession, "ended_at", candidate.metadata().get("ended_at"));
      var header = content.header();
      content =
          content.withHeader(
              new NormalizedContentHeader(
                  header.schemaVersion(),
                  header.agent(),
                  new NormalizedSessionMetadata(enrichedSession),
                  header.totals()));
      // 只有已有小列表且满足原容量的结果才显式转换；managed 即使调用少也保持流式表示。
      NormalizedSessionArtifact artifact =
          !success.hasManagedRecords()
                  && content.header().totals().values().stream()
                      .allMatch(total -> total <= NormalizedConstants.MAX_COLLECTION_SIZE)
              ? content.toArtifact()
              : null;

      // 3. 写入制品
      Map<String, String> fingerprints = SourceFingerprintMaps.forCandidate(filePath, candidate);
      WriteResult writeResult;
      try {
        Path output = Files.createDirectories(config.artifactOutputDir());
        writeResult =
            artifact == null
                ? artWriter.writeContent(output, content, fingerprints)
                : artWriter.write(output, artifact, fingerprints);
      } catch (IOException e) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.ARTIFACT_WRITE, e.getMessage());
      }

      // 4. 提交 index 写入端口
      double fileMtime = candidate.fingerprint().lastModifiedMs() / 1000.0;
      String filePathStr = filePath.toAbsolutePath().toString();
      try {
        Instant indexedAt = Instant.ofEpochMilli(System.currentTimeMillis());
        if (artifact == null) {
          indexWriter.writeNormalizedContent(
              content,
              writeResult.dataPath(),
              filePathStr,
              fileMtime,
              writeResult.contentSize(),
              indexedAt);
        } else {
          indexWriter.writeNormalizedArtifact(
              artifact,
              writeResult.dataPath(),
              filePathStr,
              fileMtime,
              writeResult.contentSize(),
              indexedAt);
        }
      } catch (RuntimeException | IOException e) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.INDEX_WRITE, exceptionMessage(e));
      }

      return new CandidateResult(CandidateOutcome.SUCCESS, null, null);

    } catch (Exception e) {
      return new CandidateResult(
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.NORMALIZE, exceptionMessage(e));
    }
  }

  private static String exceptionMessage(Throwable e) {
    String message = e.getMessage();
    if (message != null && !message.isBlank()) {
      return message;
    }
    return e.getClass().getName();
  }

  private static void putStringIfAbsent(Map<String, Object> session, String key, String value) {
    if (value == null || value.isBlank()) {
      return;
    }
    Object existing = session.get(key);
    if (existing == null || existing.toString().isBlank()) {
      session.put(key, value);
    }
  }

  static String meaningfulProject(String preferred, String fallback) {
    if (isMeaningfulProject(preferred)) {
      return preferred;
    }
    return fallback == null ? "" : fallback;
  }

  static boolean isMeaningfulProject(String value) {
    return value != null && !value.isBlank() && !".".equals(value) && !value.startsWith("./");
  }

  /**
   * 判断候选项是否为 transcript 缺失（元数据驱动发现的 fallback 场景）。
   *
   * <p>零值指纹（sizeBytes=0 且无 contentHash）表示发现阶段未找到物理源文件。
   */
  static boolean isTranscriptMissing(Candidate candidate) {
    return candidate.fingerprint().sizeBytes() == 0
        && candidate.fingerprint().contentHash().isEmpty();
  }

  /**
   * 处理 transcript 缺失的候选项：创建最小 session row（仅元数据）。
   *
   * <p>与 Python master 的 {@code _session_from_history} 对齐：使用 history timestamp 作为 ended_at，
   * 所有计数器字段填 0，不写 artifact。
   */
  static CandidateResult processTranscriptMissingCandidate(
      Candidate candidate, SourceAdapter adapter, IndexWriterPort indexWriter) {
    try {
      String sessionKey = candidate.sessionKey().replace('/', ':');
      String agentValue = adapter.sourceId().getValue();
      Map<String, String> meta = candidate.metadata();

      // 从 sessionKey 提取 sessionId（格式：agent:sessionId）
      String sessionId = sessionKey;
      int colonIdx = sessionKey.indexOf(':');
      if (colonIdx >= 0 && colonIdx < sessionKey.length() - 1) {
        sessionId = sessionKey.substring(colonIdx + 1);
      }

      String title = meta.getOrDefault("title", "");
      String projectKey = meaningfulProject(meta.getOrDefault("cwd", ""), candidate.projectKey());
      String projectName = projectKey;
      int lastSlash = projectKey.lastIndexOf('/');
      if (lastSlash >= 0 && lastSlash < projectKey.length() - 1) {
        projectName = projectKey.substring(lastSlash + 1);
      }

      String endedAt = metadataEndedAt(meta);

      // 构建最小 session 写入请求：所有计数器填 0，不写 artifact
      indexWriter.writeMissingTranscriptSession(
          new MissingTranscriptSession(
              sessionKey,
              agentValue,
              sessionId,
              title,
              projectKey,
              projectName,
              meta.getOrDefault("cwd", ""),
              meta.getOrDefault("started_at", ""),
              endedAt,
              meta.getOrDefault("git_branch", ""),
              meta.getOrDefault("model", ""),
              meta.getOrDefault("source", agentValue),
              Instant.ofEpochMilli(System.currentTimeMillis())));
      return new CandidateResult(CandidateOutcome.SUCCESS, null, null);
    } catch (Exception e) {
      return new CandidateResult(
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.INDEX_WRITE, exceptionMessage(e));
    }
  }

  /** 显式结束时间优先；仅 history timestamp 可作为已知末次活动时间。 */
  static String metadataEndedAt(Map<String, String> metadata) {
    String endedAt = metadata.getOrDefault("ended_at", "");
    if (!endedAt.isEmpty()) return endedAt;
    try {
      double timestamp = Double.parseDouble(metadata.getOrDefault("timestamp", "0"));
      if (Double.isFinite(timestamp) && timestamp > 0) {
        return Instant.ofEpochMilli((long) timestamp).toString();
      }
    } catch (NumberFormatException ignored) {
      // 无依据的时间保持未知。
    }
    return "";
  }

  /**
   * 从候选 session key 提取 provider 侧 session ID。
   *
   * <p>Codex rollout 文件名包含时间前缀（{@code rollout-...-<uuid>.jsonl}），不能作为 {@code
   * sessions.session_id}；否则页面链接和后端 API 会与 Python main 的 {@code agent:session_id} 主键不一致。仅在 session
   * key 缺少 provider ID 时才回退到文件名。
   */
  private static String extractSessionId(String sessionKey, Path filePath) {
    int colonIdx = sessionKey.indexOf(':');
    if (colonIdx >= 0 && colonIdx < sessionKey.length() - 1) {
      return sessionKey.substring(colonIdx + 1);
    }
    String fileName = filePath.getFileName().toString();
    int dotIndex = fileName.lastIndexOf('.');
    return dotIndex > 0 ? fileName.substring(0, dotIndex) : fileName;
  }

  /** 构建错误汇总。 */
  private static ScanSummary buildErrorSummary(long startMs, ScanIssue issue, long scanLogId) {
    long endMs = System.currentTimeMillis();
    return new ScanSummary(0, 0, 0, 1, endMs - startMs, scanLogId, Map.of(), List.of(issue));
  }

  /**
   * 表示 CandidateResult 数据。
   *
   * @param outcome 处理结果。
   * @param phase 处理阶段。
   * @param message 消息文本。
   * @param code 显式错误码，空字符串时使用阶段默认归类。
   */
  record CandidateResult(
      CandidateOutcome outcome, ScanIssue.ScanPhase phase, String message, String code) {
    CandidateResult(CandidateOutcome outcome, ScanIssue.ScanPhase phase, String message) {
      this(outcome, phase, message, "");
    }

    ScanIssue issue(String sessionKey, String source) {
      return new ScanIssue(sessionKey, source, phase, message, code);
    }
  }

  /** 候选项处理结果枚举。 */
  enum CandidateOutcome {
    SUCCESS,
    SKIPPED,
    ERROR
  }
}
