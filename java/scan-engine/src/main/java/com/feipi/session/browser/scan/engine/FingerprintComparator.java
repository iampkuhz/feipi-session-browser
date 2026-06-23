package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;

/**
 * 候选项指纹比较器。
 *
 * <p>实现分层指纹比较策略，避免仅依赖 mtime 导致的误判。 比较层级：
 *
 * <ol>
 *   <li>存储路径为空 → CHANGED（需要重新处理）。
 *   <li>mtime 比较：候选项 fingerprint mtime 不大于 stored mtime → UNCHANGED。
 *   <li>mtime 变新 → CHANGED。
 * </ol>
 *
 * <p>比较基于候选项 {@link SourceFingerprint} 中记录的 {@code lastModifiedMs}， 与 sessions 表中存储的 {@code
 * file_mtime}（epoch 秒）对比。 路径存在性检查在调用方（{@link IncrementalScanEngine}）完成，本类不做文件 I/O。
 */
final class FingerprintComparator {

  /** 防止实例化。 */
  private FingerprintComparator() {}

  /**
   * 比较候选项指纹与已存储指纹，返回候选项状态。
   *
   * <p>比较逻辑：
   *
   * <ol>
   *   <li>存储路径为空 → CHANGED。
   *   <li>候选项 mtime（转换为秒）不大于存储 mtime → UNCHANGED。
   *   <li>候选项 mtime 大于存储 mtime → CHANGED。
   * </ol>
   *
   * @param candidate 当前发现的候选项
   * @param stored 已存储的会话指纹
   * @return 候选项状态
   */
  static CandidateState compare(Candidate candidate, StoredSessionFingerprint stored) {
    // 如果存储路径为空，视为 changed（需要重新处理）
    if (stored.filePath().isEmpty()) {
      return CandidateState.CHANGED;
    }

    // mtime 比较：候选项 fingerprint lastModifiedMs vs stored file_mtime
    double candidateMtimeSec = candidate.fingerprint().lastModifiedMs() / 1000.0;
    double storedMtimeSec = stored.fileMtime();

    if (Double.compare(candidateMtimeSec, storedMtimeSec) <= 0) {
      return CandidateState.UNCHANGED;
    }

    return CandidateState.CHANGED;
  }
}
