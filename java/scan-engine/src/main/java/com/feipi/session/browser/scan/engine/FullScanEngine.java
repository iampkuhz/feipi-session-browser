package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.artifact.normalized.WriteResult;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.index.sqlite.ArtifactRowMapper;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.SessionArtifactRow;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.index.sqlite.WriteBatch;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
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
 *   <li>确保 SQLite schema 已就绪（{@link IndexSchema#ensureSchema}）。
 *   <li>写入 {@code scan_log} 行（{@code status = 'running'}）。
 *   <li>遍历每个源条目：安全检查 → 发现候选项 → 逐候选解析 → 归一化 → 写入制品 → 构建 index SQL。
 *   <li>通过 {@link WriteBatch} 批量提交 index 行。
 *   <li>更新 {@code scan_log} 行（{@code success} 或 {@code failure}）。
 *   <li>返回 {@link ScanSummary}。
 * </ol>
 *
 * <p>复用现有组件：
 *
 * <ul>
 *   <li>{@link NormalizationEngine} — 纯函数归一化
 *   <li>{@link NormalizedArtifactWriter} — 失败安全制品写入
 *   <li>{@link ArtifactRowMapper} — 制品到 index 行的唯一映射
 *   <li>{@link WriteBatch} — 批量 index 写入
 * </ul>
 *
 * <p>校验放置：根目录安全检查在 {@link SourceAdapter#checkRoot} 边界执行一次； 归一化制品信任 domain 不变量已验证， {@link
 * ArtifactRowMapper} 只做 DB 约束所需的非空校验。
 */
public final class FullScanEngine {

  private static final Logger log = LoggerFactory.getLogger(FullScanEngine.class);

  /** 每 N 个候选项 flush 一次 WriteBatch，防止单事务过大。 */
  private static final int FLUSH_INTERVAL = 100;

  /** sessions 表 INSERT 列清单，用于 {@link #addSessionInsert} 预构建 SQL。 */
  private static final String SESSION_INSERT_PREFIX =
      "INSERT OR REPLACE INTO sessions ("
          + "session_key, agent, session_id, title, project_key, project_name, "
          + "cwd, started_at, ended_at, duration_seconds, model_execution_seconds, "
          + "tool_execution_seconds, model, git_branch, source, "
          + "user_message_count, assistant_message_count, tool_call_count, "
          + "output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens, "
          + "total_tokens, failed_tool_count, subagent_instance_count, "
          + "indexed_at, file_mtime, file_path"
          + ") VALUES (";

  /** session_artifacts 表 INSERT 列清单，用于 {@link #addArtifactInsert} 预构建 SQL。 */
  private static final String ARTIFACT_INSERT_PREFIX =
      "INSERT OR REPLACE INTO session_artifacts ("
          + "session_key, artifact_type, path, schema_version, source_path, "
          + "source_mtime, size_bytes, created_at, updated_at"
          + ") VALUES (";

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
   * 执行全量扫描。
   *
   * <p>在单个写连接上串行完成全部操作：schema 确保 → scan_log 开始 → 逐源处理 → index 写入 → scan_log 完成。 原始 source
   * 文件只读，不做任何修改。
   *
   * @param writeConn SQLite 写连接，由调用方创建和管理生命周期
   * @param config 扫描配置
   * @return 扫描汇总结果
   * @throws NullPointerException 当参数为 null 时
   */
  public ScanSummary scan(Connection writeConn, ScanConfig config) {
    Objects.requireNonNull(writeConn, "writeConn 不得为 null");
    Objects.requireNonNull(config, "config 不得为 null");

    long startMs = System.currentTimeMillis();
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

    // 2. 开始 scan_log
    long scanLogId;
    try {
      scanLogId = ScanLogManager.startScan(writeConn, startEpoch);
    } catch (SQLException e) {
      log.error("scan_log 开始记录失败", e);
      return buildErrorSummary(startMs, "scan_log start failed: " + e.getMessage());
    }

    // 3. 处理各源
    List<ScanIssue> issues = new ArrayList<>();
    Map<com.feipi.session.browser.source.spi.SourceId, Integer> perSourceCount =
        new LinkedHashMap<>();
    Map<String, Integer> perSourceCountByValue = new LinkedHashMap<>();
    int[] counters = new int[3]; // 计数器数组：候选总数、成功数、错误与跳过数
    int skippedCount = 0;

    WriteBatch batch = new WriteBatch(writeConn, WriteBatch.DEFAULT_MAX_ENTRIES);
    boolean scanFailed = false;

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

      // 空根目录检查
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
      counters[0] += sourceCount;

      // 逐候选处理
      int processedInBatch = 0;
      for (Candidate candidate : candidates.orderedItems()) {
        CandidateResult result =
            processCandidate(
                candidate, entry.adapter(), config, batch, normalizationEngine, artifactWriter);
        switch (result.outcome) {
          case SUCCESS -> counters[1]++;
          case SKIPPED -> skippedCount++;
          case ERROR -> {
            counters[2]++;
            issues.add(
                new ScanIssue(candidate.sessionKey(), agentValue, result.phase, result.message));
          }
          default -> {}
        }
        processedInBatch++;

        // 定期 flush
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

    // 4. 最终 flush
    if (!scanFailed && batch.pendingCount() > 0) {
      try {
        batch.flush();
      } catch (SQLException e) {
        log.error("WriteBatch 最终 flush 失败", e);
        scanFailed = true;
      }
    }

    // 5. 完成 scan_log
    long endMs = System.currentTimeMillis();
    double endEpoch = endMs / 1000.0;
    try {
      if (scanFailed) {
        ScanLogManager.failScan(writeConn, scanLogId, endEpoch, perSourceCountByValue);
      } else {
        ScanLogManager.completeScan(writeConn, scanLogId, endEpoch, perSourceCountByValue);
      }
    } catch (SQLException e) {
      log.error("scan_log 完成记录失败", e);
    }

    long duration = endMs - startMs;
    return new ScanSummary(
        counters[0],
        counters[1],
        skippedCount,
        counters[2],
        duration,
        scanLogId,
        perSourceCount,
        issues);
  }

  /**
   * 处理单个候选项：解析 → 归一化 → 写入制品 → 构建 index SQL。
   *
   * <p>成功时将 INSERT SQL 添加到 WriteBatch。失败时记录问题但不中断整体扫描。
   *
   * @param candidate 待处理候选项
   * @param adapter 源适配器
   * @param config 扫描配置
   * @param batch 写入批次
   * @param normEngine 归一化引擎
   * @param artWriter 制品写入器
   * @return 候选项处理结果
   */
  static CandidateResult processCandidate(
      Candidate candidate,
      SourceAdapter adapter,
      ScanConfig config,
      WriteBatch batch,
      NormalizationEngine normEngine,
      NormalizedArtifactWriter artWriter) {

    try {
      // 1. 解析
      SourceResult parseResult = adapter.parse(candidate, null);

      if (parseResult instanceof SourceResult.Skipped skipped) {
        return new CandidateResult(
            CandidateOutcome.SKIPPED, ScanIssue.ScanPhase.PARSE, skipped.reason());
      }
      if (parseResult instanceof SourceResult.Fatal fatal) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, fatal.errorDetail());
      }
      if (parseResult instanceof SourceResult.RetryableIncomplete retryable) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, retryable.reason());
      }
      if (!(parseResult instanceof SourceResult.Success success)) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.PARSE, "Unknown parse result type");
      }

      // 2. 归一化
      Path filePath = Path.of(candidate.fingerprint().locator());
      NormalizedSourceFile sourceFile =
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT,
              filePath.toAbsolutePath(),
              Optional.empty(),
              Optional.empty());

      NormalizedAgent agent = NormalizedAgent.fromValue(adapter.sourceId().getValue());
      List<SourceDiagnostic> diagnostics = success.diagnostics();
      NormalizedSessionArtifact artifact =
          normEngine.normalize(agent, success.records(), diagnostics, List.of(sourceFile));

      // 3. 写入制品
      Map<String, String> fingerprints = buildFingerprints(filePath, candidate);
      WriteResult writeResult;
      try {
        writeResult = artWriter.write(config.artifactOutputDir(), artifact, fingerprints);
      } catch (IOException e) {
        return new CandidateResult(
            CandidateOutcome.ERROR, ScanIssue.ScanPhase.ARTIFACT_WRITE, e.getMessage());
      }

      // 4. 映射到 index 行并构建 SQL
      double fileMtime = candidate.fingerprint().lastModifiedMs() / 1000.0;
      String filePathStr = filePath.toAbsolutePath().toString();
      SessionRow sessionRow = ArtifactRowMapper.toSessionRow(artifact, fileMtime, filePathStr);

      SessionArtifactRow artifactRow =
          ArtifactRowMapper.toArtifactRow(
              sessionRow.sessionKey(),
              writeResult.dataPath().toString(),
              artifact.schemaVersion(),
              filePathStr,
              fileMtime,
              writeResult.contentSize(),
              System.currentTimeMillis() / 1000.0);

      // 5. 构建 INSERT SQL 并添加到 batch
      addSessionInsert(batch, sessionRow);
      addArtifactInsert(batch, artifactRow);

      return new CandidateResult(CandidateOutcome.SUCCESS, null, null);

    } catch (Exception e) {
      return new CandidateResult(
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.NORMALIZE, e.getMessage());
    }
  }

  /** 构建源文件指纹映射。 */
  private static Map<String, String> buildFingerprints(Path filePath, Candidate candidate) {
    Optional<String> hash = candidate.fingerprint().contentHash();
    if (hash.isPresent()) {
      return Map.of(filePath.toAbsolutePath().toString(), hash.get());
    }
    return Map.of();
  }

  /** 将会话行写入批量插入语句，使用预定义列清单避免重复拼接。 */
  private static void addSessionInsert(WriteBatch batch, SessionRow row) {
    StringBuilder sb = new StringBuilder(SESSION_INSERT_PREFIX);
    appendSqlValue(sb, row.sessionKey()).append(", ");
    appendSqlValue(sb, row.agent()).append(", ");
    appendSqlValue(sb, row.sessionId()).append(", ");
    appendSqlValue(sb, row.title()).append(", ");
    appendSqlValue(sb, row.projectKey()).append(", ");
    appendSqlValue(sb, row.projectName()).append(", ");
    appendSqlValue(sb, row.cwd()).append(", ");
    appendSqlValue(sb, row.startedAt()).append(", ");
    appendSqlValue(sb, row.endedAt()).append(", ");
    sb.append(row.durationSeconds()).append(", ");
    sb.append(row.modelExecutionSeconds()).append(", ");
    sb.append(row.toolExecutionSeconds()).append(", ");
    appendSqlValue(sb, row.model()).append(", ");
    appendSqlValue(sb, row.gitBranch()).append(", ");
    appendSqlValue(sb, row.source()).append(", ");
    sb.append(row.userMessageCount()).append(", ");
    sb.append(row.assistantMessageCount()).append(", ");
    sb.append(row.toolCallCount()).append(", ");
    sb.append(row.outputTokens()).append(", ");
    sb.append(row.freshInputTokens()).append(", ");
    sb.append(row.cacheReadTokens()).append(", ");
    sb.append(row.cacheWriteTokens()).append(", ");
    sb.append(row.totalTokens()).append(", ");
    sb.append(row.failedToolCount()).append(", ");
    sb.append(row.subagentInstanceCount()).append(", ");
    sb.append(row.indexedAt()).append(", ");
    sb.append(row.fileMtime()).append(", ");
    appendSqlValue(sb, row.filePath());
    sb.append(")");
    batch.addInsert(sb.toString());
  }

  /** 将制品行写入批量插入语句，使用预定义列清单避免重复拼接。 */
  private static void addArtifactInsert(WriteBatch batch, SessionArtifactRow row) {
    StringBuilder sb = new StringBuilder(ARTIFACT_INSERT_PREFIX);
    appendSqlValue(sb, row.sessionKey()).append(", ");
    appendSqlValue(sb, row.artifactType()).append(", ");
    appendSqlValue(sb, row.path()).append(", ");
    appendSqlValue(sb, row.schemaVersion()).append(", ");
    appendSqlValue(sb, row.sourcePath()).append(", ");
    sb.append(row.sourceMtime()).append(", ");
    sb.append(row.sizeBytes()).append(", ");
    sb.append(row.createdAt()).append(", ");
    sb.append(row.updatedAt());
    sb.append(")");
    batch.addInsert(sb.toString());
  }

  /** 将字符串值追加为 SQL 字面量（单引号转义）。 */
  private static StringBuilder appendSqlValue(StringBuilder sb, String value) {
    sb.append("'");
    sb.append(value.replace("'", "''"));
    sb.append("'");
    return sb;
  }

  /** 构建错误汇总。 */
  private static ScanSummary buildErrorSummary(long startMs, String errorMessage) {
    long endMs = System.currentTimeMillis();
    return new ScanSummary(
        0,
        0,
        0,
        0,
        endMs - startMs,
        0,
        Map.of(),
        List.of(new ScanIssue("", "", ScanIssue.ScanPhase.ROOT_CHECK, errorMessage)));
  }

  /** 候选项处理结果。 */
  record CandidateResult(CandidateOutcome outcome, ScanIssue.ScanPhase phase, String message) {}

  /** 候选项处理结果枚举。 */
  enum CandidateOutcome {
    SUCCESS,
    SKIPPED,
    ERROR
  }
}
