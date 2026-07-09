package com.feipi.session.browser.index.api.write;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;

/** 扫描编排使用的索引写侧端口。 */
public interface IndexWriterPort {

  /** 确保底层索引 schema 已可支持扫描读写。 */
  void ensureSchema();

  /** 全量重建前清空已索引的会话和 artifact 数据。 */
  void clearExistingIndex();

  /** 记录全量扫描开始，并返回创建的扫描日志 id。 */
  default long startScan(double startedAt) {
    return startScan(startedAt, "full");
  }

  /** 按指定模式记录扫描开始，并返回创建的扫描日志 id。 */
  long startScan(double startedAt, String mode);

  /** 将扫描日志标记为成功。 */
  void completeScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount);

  /** 将扫描日志标记为失败。 */
  void failScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount);

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

  /** 为缺少 transcript 的候选会话加入仅元数据写入队列。 */
  void writeMissingTranscriptSession(MissingTranscriptSession session);

  /** 返回等待 flush 的写入操作数量。 */
  int pendingWriteCount();

  /** 按实现定义的事务边界 flush 已排队写入操作。 */
  void flushPendingWrites();
}
