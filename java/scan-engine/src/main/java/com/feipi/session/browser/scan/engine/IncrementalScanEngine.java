package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.WriteBatch;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
 *   <li>确保 SQLite schema 已就绪。
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

  /** 每 N 个候选项 flush 一次 WriteBatch。 */
  private static final int FLUSH_INTERVAL = 100;

  /** 当前 scan logic 版本，变化时触发全量重建。 */
  public static final int CURRENT_SCAN_LOGIC_VERSION = 1;

  /** index_metadata 表中 scan logic version 的键名。 */
  private static final String SCAN_LOGIC_VERSION_KEY = "scan_logic_version";

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
   * @param writeConn SQLite 写连接
   * @param config 扫描配置
   * @param maxAgeSeconds 可选的会话 age 上限（秒），null 表示不过滤
   * @return 增量扫描汇总
   * @throws NullPointerException 当参数为 null 时
   */
  public IncrementalScanSummary scan(
      Connection writeConn, ScanConfig config, Double maxAgeSeconds) {
    return scan(writeConn, config, maxAgeSeconds, null);
  }

  /**
   * 执行增量扫描，支持取消。
   *
   * <p>在候选项循环中检查 cancelToken，一旦取消立即停止处理并标记 scan_log 为 failure。
   *
   * @param writeConn SQLite 写连接
   * @param config 扫描配置
   * @param maxAgeSeconds 可选的会话 age 上限（秒），null 表示不过滤
   * @param cancelToken 可选的取消令牌，null 表示不取消
   * @return 增量扫描汇总
   * @throws CancellationException 当扫描被取消时
   * @throws NullPointerException 当 writeConn 或 config 为 null 时
   */
  public IncrementalScanSummary scan(
      Connection writeConn, ScanConfig config, Double maxAgeSeconds, ScanCancelToken cancelToken) {
    Objects.requireNonNull(writeConn, "writeConn 不得为 null");
    Objects.requireNonNull(config, "config 不得为 null");

    long startMs = clock.millis();
    double startEpoch = startMs / 1000.0;

    // 确保 artifact 输出目录存在
    try {
      Files.createDirectories(config.artifactOutputDir());
    } catch (IOException e) {
      log.error("无法创建 artifact 输出目录: {}", config.artifactOutputDir(), e);
      return buildErrorSummary(startMs, e.getMessage());
    }

    // 1. 确保 schema
    try {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(writeConn);
    } catch (SQLException e) {
      log.error("schema 初始化失败", e);
      return buildErrorSummary(startMs, "Schema initialization failed: " + e.getMessage());
    }

    // 2. 开始 scan_log（incremental 模式）
    long scanLogId;
    try {
      scanLogId = ScanLogManager.startScan(writeConn, startEpoch, "incremental");
    } catch (SQLException e) {
      log.error("scan_log 开始记录失败", e);
      return buildErrorSummary(startMs, "scan_log start failed: " + e.getMessage());
    }

    boolean scanFailed = false;
    Map<String, Integer> perSourceCountByValue = new LinkedHashMap<>();
    Map<com.feipi.session.browser.source.spi.SourceId, Integer> perSourceCount =
        new LinkedHashMap<>();
    long scanLogIdFinal = scanLogId;

    try {
      // 3. 加载已索引会话指纹
      Map<String, StoredSessionFingerprint> storedFingerprints;
      try {
        storedFingerprints = FingerprintRepository.loadAll(writeConn);
      } catch (SQLException e) {
        log.error("加载已索引指纹失败", e);
        return buildErrorSummary(startMs, "Load stored fingerprints failed: " + e.getMessage());
      }

      // 4. 检查 scan logic version
      boolean rebuildTriggered = false;
      int storedVersion = loadScanLogicVersion(writeConn);
      if (storedVersion != CURRENT_SCAN_LOGIC_VERSION) {
        log.info(
            "scan logic version 变化: stored={}, current={} — 触发重建",
            storedVersion,
            CURRENT_SCAN_LOGIC_VERSION);
        rebuildTriggered = true;
      }

      // 计算 age cutoff 时间戳
      String cutoffIso = computeAgeCutoff(maxAgeSeconds);

      // 5. 处理各源
      List<ScanIssue> issues = new ArrayList<>();

      int[] stateCounts = new int[4]; // 状态计数：新增、变化、未变、可重试
      int successCount = 0;
      int errorCount = 0;
      int skippedByAgeCount = 0;
      int totalCandidates = 0;

      WriteBatch batch = new WriteBatch(writeConn, WriteBatch.DEFAULT_MAX_ENTRIES);
      int processedInBatch = 0;

      for (ScanConfig.SourceEntry entry : config.sourceEntries()) {
        String agentValue = entry.adapter().sourceId().getValue();

        // agent 过滤
        if (!config.isAgentAllowed(agentValue)) {
          log.info("跳过被过滤的源: {}", agentValue);
          continue;
        }

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
          log.info("源根目录不存在或不是目录: {} {}", agentValue, entry.rootPath());
          continue;
        }

        // 发现候选项
        BoundedStream<Candidate> candidates;
        try {
          candidates = entry.adapter().discover(entry.rootPath());
        } catch (Exception e) {
          issues.add(new ScanIssue("", agentValue, ScanIssue.ScanPhase.DISCOVERY, e.getMessage()));
          continue;
        }

        int sourceCount = candidates.size();
        perSourceCount.merge(entry.adapter().sourceId(), sourceCount, Integer::sum);
        perSourceCountByValue.merge(agentValue, sourceCount, Integer::sum);
        totalCandidates += sourceCount;

        // 逐候选处理
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
            continue;
          }

          // Age cutoff 过滤
          if (cutoffIso != null && stored != null) {
            String endedAt = stored.endedAt();
            if (!endedAt.isEmpty() && endedAt.compareTo(cutoffIso) < 0) {
              skippedByAgeCount++;
              continue;
            }
          }

          // 处理需要更新的候选项
          FullScanEngine.CandidateResult result =
              FullScanEngine.processCandidate(
                  candidate, entry.adapter(), config, batch, normalizationEngine, artifactWriter);

          switch (result.outcome()) {
            case SUCCESS -> successCount++;
            case SKIPPED -> skippedByAgeCount++;
            case ERROR -> {
              errorCount++;
              issues.add(new ScanIssue(sessionKey, agentValue, result.phase(), result.message()));
            }
          }

          processedInBatch++;
          if (processedInBatch >= FLUSH_INTERVAL && batch.pendingCount() > 0) {
            try {
              batch.flush();
            } catch (SQLException e) {
              log.error("WriteBatch flush 失败", e);
              issues.add(
                  new ScanIssue("", agentValue, ScanIssue.ScanPhase.INDEX_WRITE, e.getMessage()));
              scanFailed = true;
            }
            processedInBatch = 0;
          }
        }
      }

      // 6. 最终 flush
      if (!scanFailed && batch.pendingCount() > 0) {
        try {
          batch.flush();
        } catch (SQLException e) {
          log.error("WriteBatch 最终 flush 失败", e);
          scanFailed = true;
        }
      }

      // 7. 更新 scan logic version
      if (!scanFailed) {
        saveScanLogicVersion(writeConn, CURRENT_SCAN_LOGIC_VERSION);
      }

      // 8. 完成 scan_log
      long endMs = clock.millis();
      double endEpoch = endMs / 1000.0;
      try {
        if (scanFailed) {
          ScanLogManager.failScan(writeConn, scanLogIdFinal, endEpoch, perSourceCountByValue);
        } else {
          ScanLogManager.completeScan(writeConn, scanLogIdFinal, endEpoch, perSourceCountByValue);
        }
      } catch (SQLException e) {
        log.error("scan_log 完成记录失败", e);
      }

      long duration = endMs - startMs;
      return new IncrementalScanSummary(
          totalCandidates,
          successCount,
          skippedByAgeCount,
          errorCount,
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
      // 标记 scan_log 为失败，确保不留 running 状态
      long endMs = clock.millis();
      double endEpoch = endMs / 1000.0;
      try {
        ScanLogManager.failScan(writeConn, scanLogIdFinal, endEpoch, perSourceCountByValue);
      } catch (SQLException sqlEx) {
        log.error("取消后更新 scan_log 失败", sqlEx);
      }
      log.info("增量扫描已取消");
      throw e;
    }
  }

  /**
   * 执行增量扫描（不带 age cutoff）。
   *
   * @param writeConn SQLite 写连接
   * @param config 扫描配置
   * @return 增量扫描汇总
   */
  public IncrementalScanSummary scan(Connection writeConn, ScanConfig config) {
    return scan(writeConn, config, null);
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

  /**
   * 从 index_metadata 表加载 scan logic version。
   *
   * @param conn SQLite 连接
   * @return 存储的版本号，不存在时返回 0
   */
  private static int loadScanLogicVersion(Connection conn) {
    String sql = "SELECT value FROM index_metadata WHERE key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, SCAN_LOGIC_VERSION_KEY);
      try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
          return Integer.parseInt(rs.getString("value"));
        }
      }
    } catch (SQLException | NumberFormatException e) {
      log.debug("加载 scan logic version 失败，使用默认值 0", e);
    }
    return 0;
  }

  /**
   * 保存 scan logic version 到 index_metadata 表。
   *
   * @param conn SQLite 写连接
   * @param version 版本号
   */
  private void saveScanLogicVersion(Connection conn, int version) {
    String sql = "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, SCAN_LOGIC_VERSION_KEY);
      stmt.setString(2, String.valueOf(version));
      stmt.setDouble(3, clock.millis() / 1000.0);
      stmt.executeUpdate();
    } catch (SQLException e) {
      log.warn("保存 scan logic version 失败", e);
    }
  }

  /** 构建错误汇总。 */
  private static IncrementalScanSummary buildErrorSummary(long startMs, String errorMessage) {
    long endMs = System.currentTimeMillis();
    ScanSummary base =
        new ScanSummary(
            0,
            0,
            0,
            0,
            endMs - startMs,
            0,
            Map.of(),
            List.of(new ScanIssue("", "", ScanIssue.ScanPhase.ROOT_CHECK, errorMessage)));
    return IncrementalScanSummary.fromBase(base, 0, 0, 0, 0, false);
  }
}
