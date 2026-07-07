package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.artifact.normalized.WriteResult;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
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
import com.feipi.session.browser.source.spi.SourceFingerprintMaps;
import com.feipi.session.browser.source.spi.SourceNormalizationInputs;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
   * 执行全量扫描（无进度回调）。
   *
   * @param writeConn SQLite 写连接，由调用方创建和管理生命周期
   * @param config 扫描配置
   * @return 扫描汇总结果
   * @throws NullPointerException 当参数为 null 时
   */
  public ScanSummary scan(Connection writeConn, ScanConfig config) {
    return scan(writeConn, config, null);
  }

  /**
   * 执行全量扫描，支持进度回调。
   *
   * <p>在单个写连接上串行完成全部操作：schema 确保 → scan_log 开始 → 逐源处理 → index 写入 → scan_log 完成。 原始 source
   * 文件只读，不做任何修改。
   *
   * @param writeConn SQLite 写连接，由调用方创建和管理生命周期
   * @param config 扫描配置
   * @param progress 可选的进度回调，null 表示不报告进度
   * @return 扫描汇总结果
   * @throws NullPointerException 当 writeConn 或 config 为 null 时
   */
  public ScanSummary scan(Connection writeConn, ScanConfig config, ScanProgress progress) {
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

    // 1b. 清理旧 index 数据（full scan 每次重建完整索引，避免旧逻辑残留）
    try {
      ScanIndexMaintenance.clearExistingIndex(writeConn, log);
    } catch (SQLException e) {
      log.error("清理旧 index 失败", e);
      return buildErrorSummary(startMs, "Clear existing index failed: " + e.getMessage());
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
      counters[0] += sourceCount;

      if (progress != null) {
        progress.onSourceStart(agentValue, sourceCount);
      }

      // 逐候选处理
      int processedInBatch = 0;
      int progressCount = 0;
      int sourceSuccessCount = 0;
      for (Candidate candidate : candidates.orderedItems()) {
        CandidateResult result;

        // 零值指纹 → transcript/rollout 缺失 → 创建最小 index entry
        if (isTranscriptMissing(candidate)) {
          result = processTranscriptMissingCandidate(candidate, entry.adapter(), batch);
        } else {
          result =
              processCandidate(
                  candidate, entry.adapter(), config, batch, normalizationEngine, artifactWriter);
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
            issues.add(
                new ScanIssue(candidate.sessionKey(), agentValue, result.phase, result.message));
          }
          default -> {}
        }
        processedInBatch++;
        progressCount++;

        if (progress != null) {
          progress.onCandidateProcessed(agentValue, progressCount, sourceCount);
        }

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

      if (progress != null) {
        progress.onSourceEnd(agentValue, sourceSuccessCount);
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
      Path filePath = SourceNormalizationInputs.transcriptPath(candidate);
      List<SourceDiagnostic> diagnostics = success.diagnostics();
      NormalizedSessionArtifact artifact =
          normEngine.normalize(
              SourceNormalizationInputs.normalizedAgent(adapter),
              success.records(),
              diagnostics,
              SourceNormalizationInputs.transcriptFiles(candidate));

      // 2b. 注入 candidate 元数据到 session map（归一化引擎是纯函数，不含源特定标识）
      String safeSessionKey = candidate.sessionKey().replace('/', ':');
      String sessionId = extractSessionId(safeSessionKey, filePath);
      Map<String, Object> enrichedSession = new LinkedHashMap<>(artifact.session());
      enrichedSession.put("session_key", safeSessionKey);
      enrichedSession.put("session_id", sessionId);
      // project_key 不得为空（DB CHECK 约束），回退使用 sessionId
      String effectiveProjectKey = candidate.projectKey();
      if (effectiveProjectKey.isEmpty()) {
        effectiveProjectKey = sessionId;
      }
      enrichedSession.put("project_key", effectiveProjectKey);
      applyCandidateMetadata(enrichedSession, candidate, adapter, artifact);
      // endedAt 为必填字段；归一化引擎未提取时回退到文件修改时间（ISO-8601 格式）
      if (!enrichedSession.containsKey("ended_at")
          || enrichedSession.get("ended_at") == null
          || enrichedSession.get("ended_at").toString().isEmpty()) {
        enrichedSession.put(
            "ended_at",
            Instant.ofEpochMilli(candidate.fingerprint().lastModifiedMs())
                .atOffset(ZoneOffset.UTC)
                .toString());
      }
      // started_at 也需要 ISO-8601 fallback
      if (!enrichedSession.containsKey("started_at")
          || enrichedSession.get("started_at") == null
          || enrichedSession.get("started_at").toString().isEmpty()) {
        enrichedSession.put(
            "started_at",
            Instant.ofEpochMilli(candidate.fingerprint().lastModifiedMs())
                .atOffset(ZoneOffset.UTC)
                .toString());
      }
      artifact =
          new NormalizedSessionArtifact(
              artifact.schemaVersion(),
              artifact.agent(),
              artifact.sourceFiles(),
              Map.copyOf(enrichedSession),
              artifact.calls(),
              artifact.toolExecutions(),
              artifact.diagnostics(),
              artifact.sourceUnitCatalog(),
              artifact.sourceUnitSequences());

      // 3. 写入制品
      Map<String, String> fingerprints = SourceFingerprintMaps.forCandidate(filePath, candidate);
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
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.NORMALIZE, exceptionMessage(e));
    }
  }

  private static String exceptionMessage(Exception e) {
    String message = e.getMessage();
    if (message != null && !message.isBlank()) {
      return message;
    }
    return e.getClass().getName();
  }

  /** 构建源文件指纹映射。 */
  private static void applyCandidateMetadata(
      Map<String, Object> session,
      Candidate candidate,
      SourceAdapter adapter,
      NormalizedSessionArtifact artifact) {
    Map<String, String> meta = candidate.metadata();

    putStringIfAbsent(session, "title", meta.get("title"));
    putStringIfAbsent(session, "model", meta.get("model"));
    putStringIfAbsent(session, "git_branch", meta.get("git_branch"));
    putStringIfAbsent(
        session, "source", meta.getOrDefault("source", adapter.sourceId().getValue()));

    String cwd = meta.getOrDefault("cwd", "");
    if (!cwd.isBlank()) {
      session.put("cwd", cwd);
      if (isMeaningfulProject(cwd)) {
        session.put("project_key", cwd);
      }
    }
    String projectKey = stringValue(session.get("project_key"));
    if (!projectKey.isBlank()) {
      session.put("project_name", projectName(projectKey));
    }

    boolean hasMaterializedSubagentRecords = hasMaterializedSubagentRecords(artifact);
    TokenComponents base = tokenComponentsFromSessionOrCalls(session, artifact.calls());
    TokenComponents direct =
        new TokenComponents(
            longMeta(meta, "freshInputTokens"),
            longMeta(meta, "cacheReadTokens"),
            longMeta(meta, "cacheWriteTokens"),
            longMeta(meta, "outputTokens"));
    TokenComponents subagent =
        new TokenComponents(
            longMeta(meta, "subagentFreshInputTokens"),
            longMeta(meta, "subagentCacheReadTokens"),
            longMeta(meta, "subagentCacheWriteTokens"),
            longMeta(meta, "subagentOutputTokens"));
    if (direct.total() > 0) {
      putTokenComponents(session, direct);
    } else if (subagent.total() > 0 && !hasMaterializedSubagentRecords) {
      putTokenComponents(session, base.plus(subagent));
    }

    long directTotal = longMeta(meta, "totalTokens");
    if (directTotal > 0) {
      session.put("totalTokens", directTotal);
    }
    long subagentTotal = longMeta(meta, "subagentTotalTokens");
    if (subagentTotal > 0
        && direct.total() == 0
        && subagent.total() == 0
        && !hasMaterializedSubagentRecords) {
      long baseTotal = numberValue(session.get("totalTokens"));
      session.put("totalTokens", baseTotal + subagentTotal);
    }

    long subagentTools = longMeta(meta, "subagentToolCallCount");
    if (subagentTools > 0 && !hasMaterializedSubagentRecords) {
      long baseTools =
          session.get("toolCallCount") instanceof Number num
              ? num.longValue()
              : artifact.toolExecutions().size();
      session.put("toolCallCount", baseTools + subagentTools);
    }

    long subagentFailed = longMeta(meta, "subagentFailedToolCount");
    if (subagentFailed > 0 && !hasMaterializedSubagentRecords) {
      long baseFailed = numberValue(session.get("failedToolCount"));
      session.put("failedToolCount", baseFailed + subagentFailed);
    }

    long subagentInstances = longMeta(meta, "subagentInstanceCount");
    if (subagentInstances > 0) {
      session.put("subagentInstanceCount", subagentInstances);
    }
  }

  private static boolean hasMaterializedSubagentRecords(NormalizedSessionArtifact artifact) {
    boolean hasSubagentCall =
        artifact.calls().stream().anyMatch(call -> call.scope() == CallScope.SUBAGENT);
    if (hasSubagentCall) {
      return true;
    }
    boolean hasSubagentTool =
        artifact.toolExecutions().stream()
            .anyMatch(tool -> tool.scope() == CallScope.SUBAGENT || tool.subagentId().isPresent());
    if (hasSubagentTool) {
      return true;
    }
    return artifact.sourceFiles().stream()
        .anyMatch(
            sourceFile ->
                sourceFile.subagentId().isPresent()
                    || sourceFile.path().toString().replace('\\', '/').contains("/subagents/"));
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

  private static void putTokenComponents(Map<String, Object> session, TokenComponents components) {
    session.put("freshInputTokens", components.freshInputTokens());
    session.put("cacheReadTokens", components.cacheReadTokens());
    session.put("cacheWriteTokens", components.cacheWriteTokens());
    session.put("outputTokens", components.outputTokens());
    session.put("totalTokens", components.total());
  }

  private static TokenComponents tokenComponents(List<NormalizedCall> calls) {
    long fresh = 0;
    long cacheRead = 0;
    long cacheWrite = 0;
    long output = 0;
    for (NormalizedCall call : calls) {
      fresh += call.usage().fresh();
      cacheRead += call.usage().cacheRead();
      cacheWrite += call.usage().cacheWrite();
      output += call.usage().output();
    }
    return new TokenComponents(fresh, cacheRead, cacheWrite, output);
  }

  private static TokenComponents tokenComponentsFromSessionOrCalls(
      Map<String, Object> session, List<NormalizedCall> calls) {
    if (hasTokenOverride(session)) {
      return new TokenComponents(
          numberValue(session.get("freshInputTokens")),
          numberValue(session.get("cacheReadTokens")),
          numberValue(session.get("cacheWriteTokens")),
          numberValue(session.get("outputTokens")));
    }
    return tokenComponents(calls);
  }

  private static boolean hasTokenOverride(Map<String, Object> session) {
    return session.get("freshInputTokens") instanceof Number
        || session.get("cacheReadTokens") instanceof Number
        || session.get("cacheWriteTokens") instanceof Number
        || session.get("outputTokens") instanceof Number;
  }

  private static long longMeta(Map<String, String> meta, String key) {
    String value = meta.get(key);
    if (value == null || value.isBlank()) {
      return 0;
    }
    try {
      return Math.max(0, Long.parseLong(value));
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  private static long numberValue(Object value) {
    return value instanceof Number num ? num.longValue() : 0;
  }

  private static String stringValue(Object value) {
    return value == null ? "" : value.toString();
  }

  private static String meaningfulProject(String preferred, String fallback) {
    if (isMeaningfulProject(preferred)) {
      return preferred;
    }
    return fallback == null ? "" : fallback;
  }

  private static boolean isMeaningfulProject(String value) {
    return value != null && !value.isBlank() && !".".equals(value) && !value.startsWith("./");
  }

  private static String projectName(String projectKey) {
    if (projectKey == null || projectKey.isBlank()) {
      return "";
    }
    int lastSlash = projectKey.lastIndexOf('/');
    if (lastSlash >= 0 && lastSlash < projectKey.length() - 1) {
      return projectKey.substring(lastSlash + 1);
    }
    return projectKey;
  }

  /**
   * 表示 token 组件汇总数据，用于保存输入、cache 与输出 token 数量。
   *
   * @param freshInputTokens 当前统计口径下的 fresh input token 数量。
   * @param cacheReadTokens 当前统计口径下的 cache read token 数量。
   * @param cacheWriteTokens 当前统计口径下的 cache write token 数量。
   * @param outputTokens 当前统计口径下的 output token 数量。
   */
  private record TokenComponents(
      long freshInputTokens, long cacheReadTokens, long cacheWriteTokens, long outputTokens) {
    private long total() {
      return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    }

    private TokenComponents plus(TokenComponents other) {
      return new TokenComponents(
          freshInputTokens + other.freshInputTokens,
          cacheReadTokens + other.cacheReadTokens,
          cacheWriteTokens + other.cacheWriteTokens,
          outputTokens + other.outputTokens);
    }
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
      Candidate candidate, SourceAdapter adapter, WriteBatch batch) {
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
      // project_key 不得为空（DB CHECK 约束），回退使用 sessionId
      if (projectKey.isEmpty()) {
        projectKey = sessionId;
      }
      String projectName = projectKey;
      int lastSlash = projectKey.lastIndexOf('/');
      if (lastSlash >= 0 && lastSlash < projectKey.length() - 1) {
        projectName = projectKey.substring(lastSlash + 1);
      }

      // 使用 history timestamp 作为 ended_at
      String endedAt = "";
      String tsStr = meta.get("timestamp");
      if (tsStr != null && !tsStr.isEmpty() && !tsStr.equals("0")) {
        try {
          double tsMs = Double.parseDouble(tsStr);
          if (tsMs > 0) {
            endedAt = java.time.Instant.ofEpochMilli((long) tsMs).toString();
          }
        } catch (NumberFormatException ignored) {
          // 忽略无效 timestamp
        }
      }
      // 回退：使用当前时间
      if (endedAt.isEmpty()) {
        endedAt = java.time.Instant.now().toString();
      }

      double indexedAt = System.currentTimeMillis() / 1000.0;

      // 构建最小 session row：所有计数器填 0，不写 artifact
      SessionRow minimalRow =
          new SessionRow(
              sessionKey,
              agentValue,
              sessionId,
              title,
              projectKey,
              projectName,
              meta.getOrDefault("cwd", ""),
              endedAt,
              endedAt,
              0,
              0,
              0,
              meta.getOrDefault("model", ""),
              "",
              meta.getOrDefault("source", agentValue),
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              indexedAt,
              0,
              "");

      addSessionInsert(batch, minimalRow);
      return new CandidateResult(CandidateOutcome.SUCCESS, null, null);
    } catch (Exception e) {
      return new CandidateResult(
          CandidateOutcome.ERROR, ScanIssue.ScanPhase.INDEX_WRITE, e.getMessage());
    }
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

  /**
   * 表示 CandidateResult 数据。
   *
   * @param outcome 处理结果。
   * @param phase 处理阶段。
   * @param message 消息文本。
   */
  record CandidateResult(CandidateOutcome outcome, ScanIssue.ScanPhase phase, String message) {}

  /** 候选项处理结果枚举。 */
  enum CandidateOutcome {
    SUCCESS,
    SKIPPED,
    ERROR
  }
}
