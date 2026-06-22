package com.feipi.session.browser.contracttest.sourceSpi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link Candidate} 契约测试。
 *
 * <p>验证候选项不变量：指纹非 null、会话键非空、元数据不可变。
 */
@DisplayName("Source SPI — Candidate 契约")
class CandidateContractTest {

  private static SourceFingerprint testFingerprint() {
    return new SourceFingerprint("/test.jsonl", SourceId.CLAUDE_CODE, 100, 1000L, Optional.of("hash"));
  }

  @Test
  @DisplayName("合法候选项可正常创建")
  void validCandidateCreated() {
    Candidate c = new Candidate(testFingerprint(), "session-1", "project-a", Map.of("key", "val"));
    assertThat(c.fingerprint()).isNotNull();
    assertThat(c.sessionKey()).isEqualTo("session-1");
    assertThat(c.projectKey()).isEqualTo("project-a");
    assertThat(c.metadata()).containsEntry("key", "val");
    assertThat(c.sourceId()).isEqualTo(SourceId.CLAUDE_CODE);
  }

  @Test
  @DisplayName("空元数据合法")
  void emptyMetadataAllowed() {
    Candidate c = new Candidate(testFingerprint(), "session-1", "", Map.of());
    assertThat(c.metadata()).isEmpty();
    assertThat(c.projectKey()).isEmpty();
  }

  @Test
  @DisplayName("null 元数据规范化为空 Map")
  void nullMetadataNormalized() {
    Candidate c = new Candidate(testFingerprint(), "session-1", "proj", null);
    assertThat(c.metadata()).isEmpty();
  }

  @Test
  @DisplayName("null fingerprint 抛出 NullPointerException")
  void nullFingerprintRejected() {
    assertThatThrownBy(() -> new Candidate(null, "session-1", "proj", Map.of()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null sessionKey 抛出 NullPointerException")
  void nullSessionKeyRejected() {
    assertThatThrownBy(() -> new Candidate(testFingerprint(), null, "proj", Map.of()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("空 sessionKey 抛出 IllegalArgumentException")
  void emptySessionKeyRejected() {
    assertThatThrownBy(() -> new Candidate(testFingerprint(), "", "proj", Map.of()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("sessionKey");
  }

  @Test
  @DisplayName("元数据不可变")
  void metadataImmutable() {
    Map<String, String> mutable = new HashMap<>();
    mutable.put("key", "val");
    Candidate c = new Candidate(testFingerprint(), "session-1", "proj", mutable);
    assertThatThrownBy(() -> c.metadata().put("new", "entry"))
        .isInstanceOf(UnsupportedOperationException.class);
  }

  @Test
  @DisplayName("元数据大小超限抛出异常")
  void metadataSizeLimitEnforced() {
    Map<String, String> tooLarge = new HashMap<>();
    for (int i = 0; i < 101; i++) {
      tooLarge.put("key" + i, "val" + i);
    }
    assertThatThrownBy(
            () -> new Candidate(testFingerprint(), "session-1", "proj", tooLarge))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("metadata size");
  }

  @Test
  @DisplayName("sourceId() 委托给 fingerprint")
  void sourceIdDelegatesToFingerprint() {
    Candidate codexCandidate =
        new Candidate(
            new SourceFingerprint("/test.jsonl", SourceId.CODEX, 0, 0, Optional.empty()),
            "session-1", "", Map.of());
    assertThat(codexCandidate.sourceId()).isEqualTo(SourceId.CODEX);
  }
}
