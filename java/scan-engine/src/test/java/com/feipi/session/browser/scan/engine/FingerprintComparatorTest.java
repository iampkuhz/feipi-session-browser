package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/**
 * {@link FingerprintComparator} 单元测试。
 *
 * <p>覆盖分层指纹比较策略：空路径、mtime 比较、mtime 碰撞、元数据变化。
 */
class FingerprintComparatorTest {

  @Test
  void emptyStoredPathAndTranscriptMissingCandidateReturnsUnchanged() {
    // 双方均无物理文件且元数据相同：history-only 会话不应反复重新处理
    Candidate candidate = makeHistoryOnlyCandidate("title1", "/proj1", "1000");
    StoredSessionFingerprint stored =
        makeHistoryOnlyStored("session-1", "title1", "/proj1", "1000");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void emptyStoredPathButCandidateNowHasTranscriptReturnsChanged() {
    // stored 无文件但候选项现在有 transcript → 需要处理
    Candidate candidate = makeCandidate(200, 3000L);
    StoredSessionFingerprint stored = makeHistoryOnlyStored("session-1", "", "", "");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void metadataTitleChangeReturnsChanged() {
    // 双方均无 transcript，但 title 变化 → CHANGED
    Candidate candidate = makeHistoryOnlyCandidate("new-title", "/proj1", "1000");
    StoredSessionFingerprint stored =
        makeHistoryOnlyStored("session-1", "old-title", "/proj1", "1000");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void metadataCwdChangeReturnsChanged() {
    // 双方均无 transcript，但 cwd 变化 → CHANGED
    Candidate candidate = makeHistoryOnlyCandidate("title1", "/proj2", "1000");
    StoredSessionFingerprint stored =
        makeHistoryOnlyStored("session-1", "title1", "/proj1", "1000");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void metadataTimestampChangeReturnsChanged() {
    // 双方均无 transcript，但 timestamp 变化 → CHANGED
    Candidate candidate = makeHistoryOnlyCandidate("title1", "/proj1", "2000");
    StoredSessionFingerprint stored =
        makeHistoryOnlyStored("session-1", "title1", "/proj1", "1000");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void mtimeEqualReturnsUnchanged() {
    // 候选项 mtime（2000ms = 2.0s）不大于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 2000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 2.0, "claude_code", "", "", "", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void mtimeOlderReturnsUnchanged() {
    // 候选项 mtime（1000ms = 1.0s）小于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 1000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 2.0, "claude_code", "", "", "", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void mtimeNewerReturnsChanged() {
    // 候选项 mtime（3000ms = 3.0s）大于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 3000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 2.0, "claude_code", "", "", "", "");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void mtimeSlightlyNewerReturnsChanged() {
    // mtime 碰撞场景：候选项 mtime 仅大 1 秒
    Candidate candidate = makeCandidate(100, 2001L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 2.0, "claude_code", "", "", "", "");

    // 保守策略：任何 mtime 增长都视为 CHANGED
    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void sameSecondMillisecondChangeReturnsChanged() {
    // 同一秒内毫秒变化应被检测（long ms / 1000.0 保留毫秒精度）
    Candidate candidate1 = makeCandidate(100, 1500L);
    StoredSessionFingerprint stored1 =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 1.5, "claude_code", "", "", "", "");
    assertThat(FingerprintComparator.compare(candidate1, stored1))
        .isEqualTo(CandidateState.UNCHANGED);

    // 候选项 mtime 1501ms = 1.501s > stored 1.500s
    Candidate candidate2 = makeCandidate(100, 1501L);
    assertThat(FingerprintComparator.compare(candidate2, stored1))
        .isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void sizeDoesNotAffectMtimeDecision() {
    // size 不同但 mtime 相同 → UNCHANGED
    SourceFingerprint fp =
        new SourceFingerprint(
            "test.jsonl", SourceId.CLAUDE_CODE, 999, 2000L, Optional.empty(), Optional.empty());
    Candidate candidate = new Candidate(fp, "session-1", "proj", Map.of());
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint(
            "session-1", "/stored/path.jsonl", 2.0, "claude_code", "", "", "", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void storedSessionFingerprintValidation() {
    assertThatThrownBy(() -> new StoredSessionFingerprint("", "", 0, "agent", "", "", "", ""))
        .isInstanceOf(IllegalArgumentException.class);

    assertThatThrownBy(() -> new StoredSessionFingerprint(null, "", 0, "agent", "", "", "", ""))
        .isInstanceOf(NullPointerException.class);

    assertThatThrownBy(() -> new StoredSessionFingerprint("key", "", -1, "agent", "", "", "", ""))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void storedSessionFingerprintNullNormalization() {
    StoredSessionFingerprint fp =
        new StoredSessionFingerprint("key", null, 0, "agent", null, null, null, null);
    assertThat(fp.filePath()).isEmpty();
    assertThat(fp.endedAt()).isEmpty();
    assertThat(fp.title()).isEmpty();
    assertThat(fp.projectKey()).isEmpty();
    assertThat(fp.cwd()).isEmpty();
  }

  private static Candidate makeCandidate(long size, long mtimeMs) {
    SourceFingerprint fp =
        new SourceFingerprint(
            "test.jsonl", SourceId.CLAUDE_CODE, size, mtimeMs, Optional.empty(), Optional.empty());
    return new Candidate(fp, "session-1", "proj", Map.of());
  }

  private static Candidate makeHistoryOnlyCandidate(String title, String cwd, String timestamp) {
    SourceFingerprint fp =
        new SourceFingerprint(
            "history.jsonl", SourceId.CLAUDE_CODE, 0, 0L, Optional.empty(), Optional.empty());
    Map<String, String> meta = new HashMap<>();
    meta.put("title", title);
    meta.put("cwd", cwd);
    meta.put("timestamp", timestamp);
    return new Candidate(fp, "session-1", "proj", meta);
  }

  private static StoredSessionFingerprint makeHistoryOnlyStored(
      String sessionKey, String title, String cwd, String timestampMs) {
    String endedAt = "";
    if (timestampMs != null && !timestampMs.isEmpty() && !timestampMs.equals("0")) {
      try {
        long tsMs = Long.parseLong(timestampMs);
        if (tsMs > 0) {
          endedAt = java.time.Instant.ofEpochMilli(tsMs).toString();
        }
      } catch (NumberFormatException ignored) {
        // 忽略无效时间戳
      }
    }
    return new StoredSessionFingerprint(
        sessionKey, "", 0.0, "claude_code", endedAt, title, cwd, cwd);
  }
}
