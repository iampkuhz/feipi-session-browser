package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/**
 * {@link FingerprintComparator} 单元测试。
 *
 * <p>覆盖分层指纹比较策略：空路径、mtime 比较、mtime 碰撞。
 */
class FingerprintComparatorTest {

  @Test
  void emptyStoredPathReturnsChanged() {
    Candidate candidate = makeCandidate(100, 2000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "", 1000.0, "claude_code", "");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void mtimeEqualReturnsUnchanged() {
    // 候选项 mtime（2000ms = 2.0s）不大于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 2000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "/stored/path.jsonl", 2.0, "claude_code", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void mtimeOlderReturnsUnchanged() {
    // 候选项 mtime（1000ms = 1.0s）小于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 1000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "/stored/path.jsonl", 2.0, "claude_code", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void mtimeNewerReturnsChanged() {
    // 候选项 mtime（3000ms = 3.0s）大于存储 mtime（2.0s）
    Candidate candidate = makeCandidate(100, 3000L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "/stored/path.jsonl", 2.0, "claude_code", "");

    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void mtimeSlightlyNewerReturnsChanged() {
    // mtime 碰撞场景：候选项 mtime 仅大 1 秒
    Candidate candidate = makeCandidate(100, 2001L);
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "/stored/path.jsonl", 2.0, "claude_code", "");

    // 保守策略：任何 mtime 增长都视为 CHANGED
    assertThat(FingerprintComparator.compare(candidate, stored)).isEqualTo(CandidateState.CHANGED);
  }

  @Test
  void sizeDoesNotAffectMtimeDecision() {
    // size 不同但 mtime 相同 → UNCHANGED
    SourceFingerprint fp =
        new SourceFingerprint(
            "test.jsonl", SourceId.CLAUDE_CODE, 999, 2000L, Optional.empty(), Optional.empty());
    Candidate candidate = new Candidate(fp, "session-1", "proj", Map.of());
    StoredSessionFingerprint stored =
        new StoredSessionFingerprint("session-1", "/stored/path.jsonl", 2.0, "claude_code", "");

    assertThat(FingerprintComparator.compare(candidate, stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void storedSessionFingerprintValidation() {
    assertThatThrownBy(() -> new StoredSessionFingerprint("", "", 0, "agent", ""))
        .isInstanceOf(IllegalArgumentException.class);

    assertThatThrownBy(() -> new StoredSessionFingerprint(null, "", 0, "agent", ""))
        .isInstanceOf(NullPointerException.class);

    assertThatThrownBy(() -> new StoredSessionFingerprint("key", "", -1, "agent", ""))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void storedSessionFingerprintNullNormalization() {
    StoredSessionFingerprint fp = new StoredSessionFingerprint("key", null, 0, "agent", null);
    assertThat(fp.filePath()).isEmpty();
    assertThat(fp.endedAt()).isEmpty();
  }

  private static Candidate makeCandidate(long size, long mtimeMs) {
    SourceFingerprint fp =
        new SourceFingerprint(
            "test.jsonl", SourceId.CLAUDE_CODE, size, mtimeMs, Optional.empty(), Optional.empty());
    return new Candidate(fp, "session-1", "proj", Map.of());
  }
}
