package com.feipi.session.browser.index.api.write;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import java.io.IOException;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 扫描编排使用的索引写侧端口。 */
public interface IndexWriterPort {

  /** 确保底层索引 schema 已可支持扫描读写。 */
  void ensureSchema();

  /** 全量重建前清空已索引的会话和 artifact 数据。 */
  void clearExistingIndex();

  /**
   * 仅清理指定 agent 的会话、artifact 和候选元数据；空集沿用全量清理。
   *
   * @param agents 明确选择的 agent 协议值，空集表示全部
   * @throws UnsupportedOperationException 旧实现不能安全执行非空来源隔离时明确失败
   */
  default void clearExistingIndex(Set<String> agents) {
    Objects.requireNonNull(agents, "agents 不得为 null");
    if (!agents.isEmpty())
      throw new UnsupportedOperationException("Scoped index clearing is not supported");
    clearExistingIndex();
  }

  /** 记录全量扫描开始，并返回创建的扫描日志 id。 */
  default long startScan(double startedAt) {
    return startScan(startedAt, "full");
  }

  /** 记录扫描开始并开启隔离写入范围；后续 flush 不得向读者发布未完成的扫描。 */
  long startScan(double startedAt, String mode);

  /** 原子发布扫描写入、逻辑版本及成功日志。 */
  void completeScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount);

  /** 放弃扫描内写入、保留此前有效索引及版本，并持久化失败日志。 */
  void failScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount);

  /**
   * 回滚扫描并保存安全失败原因；兼容不支持详情的旧写端口。
   *
   * @param scanLogId 扫描日志标识
   * @param finishedAt 结束时间
   * @param perSourceCount 已处理数量，不代表已发布数量
   * @param failures 安全失败原因
   */
  default void failScan(
      long scanLogId,
      double finishedAt,
      Map<String, Integer> perSourceCount,
      java.util.List<ScanFailure> failures) {
    failScan(scanLogId, finishedAt, perSourceCount);
  }

  /**
   * 按失败候选或阶段问题数量回滚扫描；诊断明细数量可大于错误数量。
   *
   * @param scanLogId 扫描日志标识
   * @param finishedAt 结束时间
   * @param perSourceCount 已处理数量，不代表已发布数量
   * @param errorCount 失败候选或阶段问题数量，与扫描汇总口径一致
   * @param failures 安全诊断明细，不用于推算错误数量
   */
  default void failScan(
      long scanLogId,
      double finishedAt,
      Map<String, Integer> perSourceCount,
      int errorCount,
      java.util.List<ScanFailure> failures) {
    failScan(scanLogId, finishedAt, perSourceCount, failures);
  }

  /** 加载索引中已有会话的 fingerprint。 */
  Map<String, StoredSessionFingerprint> loadStoredSessionFingerprints();

  /** 加载当前扫描逻辑版本；未保存值时返回 {@code 0}。 */
  int loadScanLogicVersion();

  /** 持久化当前扫描逻辑版本。 */
  void saveScanLogicVersion(int version, Instant updatedAt);

  /** 将一个标准化会话 artifact 及其可索引元数据加入待持久化队列。 */
  void writeNormalizedArtifact(
      NormalizedSessionArtifact artifact,
      Path artifactPath,
      String sourcePath,
      double sourceMtime,
      long sizeBytes,
      Instant indexedAt);

  /** 写入一个完整逻辑会话，不要求先构造旧格式制品。 */
  default void writeNormalizedContent(
      NormalizedSessionContent content,
      Path artifactPath,
      String sourcePath,
      double sourceMtime,
      long sizeBytes,
      Instant indexedAt)
      throws IOException {
    throw new UnsupportedOperationException("Logical session content writing is not supported");
  }

  /** 为缺少 transcript 的候选会话加入仅元数据写入队列。 */
  void writeMissingTranscriptSession(MissingTranscriptSession session);

  /** 返回等待 flush 的写入操作数量。 */
  int pendingWriteCount();

  /** 执行已排队写入；扫描范围内仅暂存，completeScan 才能发布。 */
  void flushPendingWrites();
}
