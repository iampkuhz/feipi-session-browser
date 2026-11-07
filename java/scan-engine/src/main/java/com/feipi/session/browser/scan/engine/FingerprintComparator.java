package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;

/**
 * 候选项指纹比较器。
 *
 * <p>实现分层指纹比较策略，避免仅依赖 mtime 导致的误判。 比较层级：
 *
 * <ol>
 *   <li>存储路径为空且候选项也无 transcript → 比较元数据（title/projectKey/cwd/endedAt），有变化则 CHANGED，否则 UNCHANGED。
 *   <li>存储路径为空但候选项有 transcript → CHANGED（transcript 后来出现，需要处理）。
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
   *   <li>存储路径为空且候选项也无 transcript → 比较元数据，有变化则 CHANGED，否则 UNCHANGED。
   *   <li>存储路径为空但候选项有 transcript → CHANGED。
   *   <li>候选项 mtime（转换为秒）不大于存储 mtime → UNCHANGED。
   *   <li>候选项 mtime 大于存储 mtime → CHANGED。
   * </ol>
   *
   * @param candidate 当前发现的候选项
   * @param stored 已存储的会话指纹
   * @return 候选项状态
   */
  static CandidateState compare(Candidate candidate, StoredSessionFingerprint stored) {
    if (stored.filePath().isEmpty()) {
      if (FullScanEngine.isTranscriptMissing(candidate)) {
        if (metadataChanged(candidate, stored)) {
          return CandidateState.CHANGED;
        }
        return CandidateState.UNCHANGED;
      }
      return CandidateState.CHANGED;
    }

    double candidateMtimeSec = candidate.fingerprint().lastModifiedMs() / 1000.0;
    double storedMtimeSec = stored.fileMtime();

    if (Double.compare(candidateMtimeSec, storedMtimeSec) <= 0) {
      return CandidateMetadataFingerprint.changed(candidate, stored.candidateMetadataFingerprint())
          ? CandidateState.CHANGED
          : CandidateState.UNCHANGED;
    }

    return CandidateState.CHANGED;
  }

  /**
   * 比较候选项元数据与已存储元数据是否发生变化。
   *
   * <p>用于 history-only 会话检测 title/projectKey/cwd/endedAt 的变化。 projectKey 比较复用 {@link
   * FullScanEngine#meaningfulProject} 逻辑，确保与入库语义一致。
   */
  private static boolean metadataChanged(Candidate candidate, StoredSessionFingerprint stored) {
    java.util.Map<String, String> meta = candidate.metadata();
    String candidateTitle = meta.getOrDefault("title", "");
    String candidateCwd = meta.getOrDefault("cwd", "");

    if (!candidateTitle.equals(stored.title())) {
      return true;
    }
    if (!candidateCwd.equals(stored.cwd())) {
      return true;
    }

    // projectKey 比较：复用 FullScanEngine.meaningfulProject 逻辑
    String candidateProjectKey =
        FullScanEngine.meaningfulProject(candidateCwd, candidate.projectKey());
    if (!candidateProjectKey.equals(stored.projectKey())) {
      return true;
    }

    if (!meta.getOrDefault("started_at", "").equals(stored.startedAt())
        || !meta.getOrDefault("git_branch", "").equals(stored.gitBranch())
        || !meta.getOrDefault("model", "").equals(stored.model())
        || !meta.getOrDefault("source", stored.agent()).equals(stored.source())) {
      return true;
    }
    return !FullScanEngine.metadataEndedAt(meta).equals(stored.endedAt());
  }
}
