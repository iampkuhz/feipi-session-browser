package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.IndexWriterPort;
import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.NormalizedArtifactWriter;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CancellationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Java 增量扫描引擎。
 *
 * <p>实现候选项 fingerprint 状态机：对每个发现的候选项，与已索引数据进行指纹比较， 分类为 {@link
 * CandidateState}（NEW/UNCHANGED/CHANGED/RETRYABLE）， 仅处理需要更新的候选项，跳过未变化的会话。
 *
 * <p>处理管线：
 *
 * <ol>
 *   <li>确保 index schema 已就绪。
 *   <li>写入 {@code scan_log} 行（{@code mode = 'incremental'}）。
 *   <li>加载 sessions 表中全部已索引会话的指纹数据。
 *   <li>检查 scan logic version，判断是否需要重建。
 *   <li>遍历每个源条目：发现候选项 → 状态分类 → age cutoff 过滤 → 处理需要更新的候选项。
 *   <li>更新 scan logic version。
 *   <li>完成 {@code scan_log} 行。
 *   <li>返回 {@link IncrementalScanSummary}。
 * </ol>
 *
 * <p>复用 {@link FullScanEngine#processCandidate} 进行实际的解析→归一化→写入管线。
 *
 * <p>校验放置：根目录安全检查在 {@link SourceAdapter#checkRoot} 边界执行一次； 指纹比较依赖 {@link FingerprintComparator}
 * 分层策略， 不在本层重复 size/mtime 比较。
 */
public final class IncrementalScanEngine {

  private static final Logger log = LoggerFactory.getLogger(IncrementalScanEngine.class);

  /** 每 N 个候选项 flush 一次 index writer。 */
  private static final int FLUSH_INTERVAL = 100;

  /** 当前扫描逻辑版本；重建显式用户边界后的工具归属，并保留来源identity、事件日与计量语义。 */
  public static final int CURRENT_SCAN_LOGIC_VERSION = 19;

  private final NormalizationEngine normalizationEngine;
  private final NormalizedArtifactWriter artifactWriter;
  private final Clock clock;

  /** 使用默认归一化引擎、制品写入器和系统时钟创建增量扫描引擎。 */
  public IncrementalScanEngine() {
    this(new NormalizationEngine(), new NormalizedArtifactWriter(), Clock.systemUTC());
  }

  /**
   * 使用指定的归一化引擎和制品写入器创建增量扫描引擎。
   *
   * <p>用于测试注入。时钟使用系统 UTC 时钟。
   *
   * @param normalizationEngine 归一化引擎
   * @param artifactWriter 制品写入器
   */
  public IncrementalScanEngine(
      NormalizationEngine normalizationEngine, NormalizedArtifactWriter artifactWriter) {
    this(normalizationEngine, artifactWriter, Clock.systemUTC());
  }

  /**
   * 使用指定的归一化引擎、制品写入器和时钟创建增量扫描引擎。
   *
   * <p>完整构造器，用于测试注入 fake clock。
   *
   * @param normalizationEngine 归一化引擎
   * @param artifactWriter 制品写入器
   * @param clock 时间源
   */
  public IncrementalScanEngine(
      NormalizationEngine normalizationEngine,
      NormalizedArtifactWriter artifactWriter,
      Clock clock) {
    this.normalizationEngine =
        Objects.requireNonNull(normalizationEngine, "normalizationEngine 不得为 null");
    this.artifactWriter = Objects.requireNonNull(artifactWriter, "artifactWriter 不得为 null");
    this.clock = Objects.requireNonNull(clock, "clock 不得为 null");
  }

  /**
   * 执行增量扫描。
   *
   * <p>与 full scan 不同，增量扫描先加载已索引指纹，对每个候选项进行状态分类， 仅处理 NEW、CHANGED 和 RETRYABLE 状态的候选项。 UNCHANGED
   * 候选项不触发任何 artifact 或 index 写入。
   *
   * @param indexWriter index 写入端口
   * @param config 扫描配置
   * @param maxAgeSeconds 可选的会话 age 上限（秒），null 表示不过滤
   * @return 增量扫描汇总
   * @throws NullPointerException 当参数为 null 时
   */
  public IncrementalScanSummary scan(
      IndexWriterPort indexWriter, ScanConfig config, Double maxAgeSeconds) {
    return scan(indexWriter, config, maxAgeSeconds, null);
  }

  /**
   * 执行增量扫描，支持取消。
   *
   * <p>在候选项循环中检查 cancelToken，一旦取消立即停止处理并标记 scan_log 为 failure。
   *
   * @param indexWriter index 写入端口
   * @param config 扫描配置
   * @param maxAgeSeconds 可选的会话 age 上限（秒），null 表示不过滤
   * @param cancelToken 可选的取消令牌，null 表示不取消
   * @return 增量扫描汇总
   * @throws CancellationException 当扫描被取消时
   * @throws NullPointerException 当 indexWriter 或 config 为 null 时
   */
  public IncrementalScanSummary scan(
      IndexWriterPort indexWriter,
      ScanConfig config,
      Double maxAgeSeconds,
      ScanCancelToken cancelToken) {
    return scan(indexWriter, config, maxAgeSeconds, cancelToken, null);
  }

  /**
   * 执行增量扫描，支持取消和进度回调。
   *
   * <p>在候选项循环中检查 cancelToken，一旦取消立即停止处理并标记 scan_log 为 failure。 通过 progress 参数报告每个源的处理进度。
   *
   * @param indexWriter index 写入端口
   * @param config 扫描配置
   * @param maxAgeSeconds 可选的会话 age 上限（秒），null 表示不过滤
   * @param cancelToken 可选的取消令牌，null 表示不取消
   * @param progress 可选的进度回调，null 表示不报告进度
   * @return 增量扫描汇总
   * @throws CancellationException 当扫描被取消时
   * @throws NullPointerException 当 indexWriter 或 config 为 null 时
   */
  public IncrementalScanSummary scan(
      IndexWriterPort indexWriter,
      ScanConfig config,
      Double maxAgeSeconds,
      ScanCancelToken cancelToken,
      ScanProgress progress) {
    var fatal = new ScanFatalDiagnostics("incremental");
    try {
      return scan(indexWriter, config, maxAgeSeconds, cancelToken, progress, fatal);
    } catch (Error error) {
      fatal.report(error);
      throw error;
    }
  }

  private IncrementalScanSummary scan(
      IndexWriterPort indexWriter,
      ScanConfig config,
      Double maxAgeSeconds,
      ScanCancelToken cancelToken,
      ScanProgress progress,
      ScanFatalDiagnostics fatal) {
    Objects.requireNonNull(indexWriter, "indexWriter 不得为 null");
    Objects.requireNonNull(config, "config 不得为 null");

    long startNanos = System.nanoTime();
    long startMs = clock.millis();
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
    // 2. 开始 scan_log（incremental 模式）
    long scanLogId;
    try {
      scanLogId = indexWriter.startScan(startEpoch, "incremental");
    } catch (RuntimeException e) {
      return buildErrorSummary(
          startMs,
          fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_LOG_START_FAILED", e),
          fatal.scanLogId());
    }

    boolean scanFailed = false;
    Map<String, Integer> perSourceCountByValue = new LinkedHashMap<>();
    Map<com.feipi.session.browser.source.spi.SourceId, Integer> perSourceCount =
        new LinkedHashMap<>();
    long scanLogIdFinal = scanLogId;
    fatal.scanStarted(scanLogId);
    boolean scanLogFinalized = false;

    fatal.at("INDEX_PREPARE", "");
    try {
      // 3. 加载已索引会话指纹
      Map<String, StoredSessionFingerprint> storedFingerprints;
      try {
        long phaseStart = System.nanoTime();
        if (progress != null) progress.onPhaseStart("load_fingerprints");
        storedFingerprints = indexWriter.loadStoredSessionFingerprints();
        if (progress != null)
          progress.onPhaseEnd("load_fingerprints", (System.nanoTime() - phaseStart) / 1_000_000);
      } catch (RuntimeException e) {
        return buildErrorSummary(
            startMs,
            fatal.setupFailure(ScanIssue.ScanPhase.INDEX_READ, "SCAN_FINGERPRINT_LOAD_FAILED", e),
            fatal.scanLogId());
      }

      // 4. 检查 scan logic version
      boolean rebuildTriggered = false;
      int storedVersion = indexWriter.loadScanLogicVersion();
      if (storedVersion != CURRENT_SCAN_LOGIC_VERSION) {
        log.debug(
            "scan logic version 变化: stored={}, current={} — 触发重建 (已索引 {} 个会话)",
            storedVersion,
            CURRENT_SCAN_LOGIC_VERSION,
            storedFingerprints.size());
        rebuildTriggered = true;

        // 仅重建所选来源，未扫描来源及全局旧版本保持不动。
        try {
          long phaseStart = System.nanoTime();
          if (progress != null) progress.onPhaseStart("clear_index");
          indexWriter.clearExistingIndex(config.agentFilter());
          if (progress != null)
            progress.onPhaseEnd("clear_index", (System.nanoTime() - phaseStart) / 1_000_000);
          storedFingerprints = Map.of(); // 清空内存指纹缓存
        } catch (RuntimeException e) {
          return buildErrorSummary(
              startMs,
              fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_INDEX_PREPARE_FAILED", e),
              fatal.scanLogId());
        }
      }

      // 计算 age cutoff 时间戳
      // scan logic 版本变化会先清空旧索引，此时必须完整重建；若继续套用 hot/warm
      // cutoff，会把窗口外的历史会话永久从索引中删除。
      String cutoffIso = rebuildTriggered ? null : computeAgeCutoff(maxAgeSeconds);

      // 5. 处理各源
      List<ScanIssue> issues = new ArrayList<>();

      int[] stateCounts = new int[4]; // 状态计数：新增、变化、未变、可重试
      int successCount = 0;
      int errorCount = 0;
      int skippedByAgeCount = 0;
      int totalCandidates = 0;

      int processedInBatch = 0;

      for (ScanConfig.SourceEntry entry : config.sourceEntries()) {
        String agentValue = entry.adapter().sourceId().getValue();

        // agent 过滤
        if (!config.isAgentAllowed(agentValue)) {
          log.debug("跳过被过滤的源: {}", agentValue);
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

        if (!Files.isDirectory(entry.rootPath())) {
          log.debug("源根目录不存在或不是目录: {}", agentValue);
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
        totalCandidates += sourceCount;

        if (progress != null) {
          progress.onSourceStart(agentValue, sourceCount);
        }

        fatal.at("CANDIDATE", agentValue);
        // 逐候选处理
        int progressCount = 0;
        int sourceSuccessCount = 0;
        for (Candidate candidate : candidates.orderedItems()) {
          // 取消检查
          if (cancelToken != null) {
            cancelToken.throwIfCancelled();
          }

          String sessionKey = candidate.sessionKey();
          StoredSessionFingerprint stored = storedFingerprints.get(sessionKey);

          // 状态分类
          CandidateState state;
          if (stored == null) {
            state = CandidateState.NEW;
          } else if (rebuildTriggered) {
            // scan logic version 变化，全部视为 CHANGED
            state = CandidateState.CHANGED;
          } else {
            state = FingerprintComparator.compare(candidate, stored);
          }

          // 记录状态计数
          switch (state) {
            case NEW -> stateCounts[0]++;
            case CHANGED -> stateCounts[1]++;
            case UNCHANGED -> stateCounts[2]++;
            case RETRYABLE -> stateCounts[3]++;
          }

          // UNCHANGED 不读写 artifact/DB
          if (state == CandidateState.UNCHANGED && !rebuildTriggered) {
            progressCount++;
            if (progress != null) {
              progress.onCandidateProcessed(agentValue, progressCount, sourceCount);
            }
            continue;
          }

          // Age cutoff 过滤
          if (cutoffIso != null) {
            boolean skipByAge = false;
            if (stored != null) {
              // 已索引候选：使用 stored.endedAt
              String endedAt = stored.endedAt();
              if (!endedAt.isEmpty() && endedAt.compareTo(cutoffIso) < 0) {
                skipByAge = true;
              }
            } else {
              // NEW 候选：使用 fingerprint.lastModifiedMs
              long lastModifiedMs = candidate.fingerprint().lastModifiedMs();
              if (lastModifiedMs > 0) {
                Instant lastModified = Instant.ofEpochMilli(lastModifiedMs);
                Instant cutoffInstant = Instant.parse(cutoffIso);
                if (lastModified.isBefore(cutoffInstant)) {
                  skipByAge = true;
                }
              }
            }
            if (skipByAge) {
              skippedByAgeCount++;
              progressCount++;
              if (progress != null) {
                progress.onCandidateProcessed(agentValue, progressCount, sourceCount);
              }
              continue;
            }
          }

          // 处理需要更新的候选项
          FullScanEngine.CandidateResult result;
          if (FullScanEngine.isTranscriptMissing(candidate)) {
            result =
                FullScanEngine.processTranscriptMissingCandidate(
                    candidate, entry.adapter(), indexWriter);
          } else {
            result =
                FullScanEngine.processCandidate(
                    candidate,
                    entry.adapter(),
                    config,
                    indexWriter,
                    normalizationEngine,
                    artifactWriter);
          }

          switch (result.outcome()) {
            case SUCCESS -> {
              successCount++;
              sourceSuccessCount++;
              perSourceCount.merge(entry.adapter().sourceId(), 1, Integer::sum);
              perSourceCountByValue.merge(agentValue, 1, Integer::sum);
            }
            case SKIPPED -> skippedByAgeCount++;
            case ERROR -> {
              errorCount++;
              issues.add(result.issue(sessionKey, agentValue));
            }
          }

          processedInBatch++;
          progressCount++;
          if (progress != null) {
            progress.onCandidateProcessed(agentValue, progressCount, sourceCount);
          }

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

      // 6. 最终 flush
      fatal.at("INDEX_FLUSH", "");
      if (!scanFailed && indexWriter.pendingWriteCount() > 0) {
        if (!ScanFlush.flush(indexWriter, progress, "flush_final", "", issues)) {
          scanFailed = true;
        }
      }

      scanFailed = scanFailed || !issues.isEmpty() || errorCount > 0;

      // 7. 完成 scan_log
      fatal.at("SCAN_LOG_FINISH", "");
      long endMs = clock.millis();
      double endEpoch = endMs / 1000.0;
      try {
        if (scanFailed) {
          indexWriter.failScan(
              scanLogIdFinal,
              endEpoch,
              perSourceCountByValue,
              Math.max(errorCount, issues.size()),
              ScanDiagnostics.failures(issues));
        } else {
          if (config.agentFilter().isEmpty()) {
            indexWriter.saveScanLogicVersion(CURRENT_SCAN_LOGIC_VERSION, clock.instant());
          }
          indexWriter.completeScan(scanLogIdFinal, endEpoch, perSourceCountByValue);
        }
        scanLogFinalized = true;
      } catch (RuntimeException e) {
        issues.add(
            fatal.setupFailure(ScanIssue.ScanPhase.INDEX_WRITE, "SCAN_LOG_FINISH_FAILED", e));
        scanFailed = true;
      }

      long duration = endMs - startMs;
      log.debug(
          "增量扫描完成: 候选={} 新增={} 变化={} 未变={} 跳过={} 错误={} 耗时={}ms",
          totalCandidates,
          stateCounts[0],
          stateCounts[1],
          stateCounts[2],
          skippedByAgeCount,
          errorCount,
          (System.nanoTime() - startNanos) / 1_000_000);
      return new IncrementalScanSummary(
          totalCandidates,
          successCount,
          skippedByAgeCount,
          Math.max(errorCount, issues.size()),
          duration,
          scanLogIdFinal,
          perSourceCount,
          issues,
          stateCounts[2], // 未变计数
          stateCounts[1], // 变化计数
          stateCounts[0], // 新增计数
          stateCounts[3], // 重试计数
          rebuildTriggered);

    } catch (CancellationException e) {
      scanLogFinalized = false;
      log.info("增量扫描已取消");
      throw e;
    } catch (Error error) {
      fatal.report(error);
      throw error;
    } finally {
      if (!scanLogFinalized) {
        long endMs = clock.millis();
        double endEpoch = endMs / 1000.0;
        try {
          indexWriter.failScan(scanLogIdFinal, endEpoch, perSourceCountByValue, fatal.failures());
        } catch (RuntimeException writeEx) {
          log.error("scan_log 最终标记失败: exception={}", writeEx.getClass().getName());
        } catch (Error cleanup) {
          if (!fatal.hasReportedJvmError()) throw cleanup;
          log.error("scan_log 最终标记失败: exception={}", cleanup.getClass().getName());
        }
      }
    }
  }

  /**
   * 执行增量扫描（不带 age cutoff）。
   *
   * @param indexWriter index 写入端口
   * @param config 扫描配置
   * @return 增量扫描汇总
   */
  public IncrementalScanSummary scan(IndexWriterPort indexWriter, ScanConfig config) {
    return scan(indexWriter, config, null);
  }

  /**
   * 计算 age cutoff 的 ISO 时间戳。
   *
   * @param maxAgeSeconds 会话 age 上限（秒），null 表示不过滤
   * @return ISO 8601 时间戳字符串，null 表示不过滤
   */
  private String computeAgeCutoff(Double maxAgeSeconds) {
    if (maxAgeSeconds == null || maxAgeSeconds <= 0) {
      return null;
    }
    Instant cutoff = clock.instant().minusSeconds(maxAgeSeconds.longValue());
    return cutoff.toString();
  }

  /** 构建错误汇总。 */
  private static IncrementalScanSummary buildErrorSummary(
      long startMs, ScanIssue issue, long scanLogId) {
    long endMs = System.currentTimeMillis();
    ScanSummary base =
        new ScanSummary(0, 0, 0, 1, endMs - startMs, scanLogId, Map.of(), List.of(issue));
    return IncrementalScanSummary.fromBase(base, 0, 0, 0, 0, false);
  }
}
