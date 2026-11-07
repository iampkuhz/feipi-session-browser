package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class CandidateMetadataFingerprintTest {
  @Test
  void parsedPriorityDoesNotCauseReindexLoopAndMissingInputsDoNotInventChanges() {
    Candidate original = candidate(Map.of("title", "candidate-title", "model", "candidate-model"));
    var stored = stored(CandidateMetadataFingerprint.from(original));
    assertThat(FingerprintComparator.compare(original, stored)).isEqualTo(CandidateState.UNCHANGED);
    Candidate changed =
        candidate(Map.of("title", "new-candidate-title", "model", "candidate-model"));
    assertThat(FingerprintComparator.compare(changed, stored)).isEqualTo(CandidateState.CHANGED);
    assertThat(
            FingerprintComparator.compare(
                changed, stored(CandidateMetadataFingerprint.from(candidate(Map.of())))))
        .isEqualTo(CandidateState.CHANGED);
    // 重算后 parsed 标题/模型仍优先；刷新的是候选输入摘要，不能与 parsed 值持续比较。
    assertThat(
            FingerprintComparator.compare(
                changed, stored(CandidateMetadataFingerprint.from(changed))))
        .isEqualTo(CandidateState.UNCHANGED);
    assertThat(FingerprintComparator.compare(candidate(Map.of()), stored))
        .isEqualTo(CandidateState.UNCHANGED);
  }

  @Test
  void boundariesAndInputOrderAreStableAndPlaintextIsNotStored() {
    var first = candidate(Map.of("title", "a;model=b", "model", "c"));
    var second = candidate(Map.of("model", "c", "title", "a;model=b"));
    String value = CandidateMetadataFingerprint.from(first);
    assertThat(value).isEqualTo(CandidateMetadataFingerprint.from(second));
    assertThat(value).doesNotContain("a;model=b");
    assertThat(value)
        .isNotEqualTo(
            CandidateMetadataFingerprint.from(candidate(Map.of("title", "a", "model", "b;c"))));
  }

  private Candidate candidate(Map<String, String> metadata) {
    return new Candidate(
        new SourceFingerprint(
            "synthetic.jsonl", SourceId.CODEX, 1, 1000, Optional.empty(), Optional.empty()),
        "codex:parsed-priority",
        "",
        metadata);
  }

  private StoredSessionFingerprint stored(String fingerprint) {
    return new StoredSessionFingerprint(
        "codex:parsed-priority",
        "synthetic.jsonl",
        1,
        "codex",
        "parsed-end",
        "parsed-title",
        "parsed-project",
        "parsed-cwd",
        "parsed-start",
        "parsed-branch",
        "parsed-model",
        "parsed-source",
        fingerprint);
  }
}
