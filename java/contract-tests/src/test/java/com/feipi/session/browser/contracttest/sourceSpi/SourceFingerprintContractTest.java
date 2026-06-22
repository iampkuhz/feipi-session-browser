package com.feipi.session.browser.contracttest.sourcespi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceFingerprint} 契约测试。
 *
 * <p>验证指纹不变量：路径非空、源标识非 null、数值非负、 内容哈希一致性比较和 mtime 非唯一证据。
 */
@DisplayName("Source SPI — SourceFingerprint 契约")
class SourceFingerprintContractTest {

  @Test
  @DisplayName("合法指纹可正常创建")
  void validFingerprintCreated() {
    SourceFingerprint fp =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CLAUDE_CODE, 1024, 1700000L, Optional.of("sha256:abc"));
    assertThat(fp.path()).isEqualTo("/data/test.jsonl");
    assertThat(fp.sourceId()).isEqualTo(SourceId.CLAUDE_CODE);
    assertThat(fp.sizeBytes()).isEqualTo(1024);
    assertThat(fp.lastModifiedMs()).isEqualTo(1700000L);
    assertThat(fp.contentHash()).contains("sha256:abc");
  }

  @Test
  @DisplayName("空 contentHash 可选")
  void emptyContentHashAllowed() {
    SourceFingerprint fp =
        new SourceFingerprint("/data/test.jsonl", SourceId.CODEX, 512, 1000L, Optional.empty());
    assertThat(fp.contentHash()).isEmpty();
  }

  @Test
  @DisplayName("null path 抛出 NullPointerException")
  void nullPathRejected() {
    assertThatThrownBy(() -> new SourceFingerprint(null, SourceId.QODER, 0, 0, Optional.empty()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("空 path 抛出 IllegalArgumentException")
  void emptyPathRejected() {
    assertThatThrownBy(() -> new SourceFingerprint("", SourceId.QODER, 0, 0, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("path");
  }

  @Test
  @DisplayName("负 sizeBytes 抛出 IllegalArgumentException")
  void negativeSizeRejected() {
    assertThatThrownBy(
            () -> new SourceFingerprint("/test", SourceId.QODER, -1, 0, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("sizeBytes");
  }

  @Test
  @DisplayName("负 lastModifiedMs 抛出 IllegalArgumentException")
  void negativeMtimeRejected() {
    assertThatThrownBy(
            () -> new SourceFingerprint("/test", SourceId.QODER, 0, -1, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("lastModifiedMs");
  }

  @Test
  @DisplayName("空字符串 contentHash 抛出 IllegalArgumentException")
  void emptyStringHashRejected() {
    assertThatThrownBy(() -> new SourceFingerprint("/test", SourceId.QODER, 0, 0, Optional.of("")))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("contentHash");
  }

  @Test
  @DisplayName("sameFile 比较路径和源标识")
  void sameFileComparesPathAndSource() {
    SourceFingerprint a =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CLAUDE_CODE, 100, 1000L, Optional.of("h1"));
    SourceFingerprint b =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CLAUDE_CODE, 200, 2000L, Optional.of("h2"));
    SourceFingerprint c =
        new SourceFingerprint(
            "/data/other.jsonl", SourceId.CLAUDE_CODE, 100, 1000L, Optional.empty());

    assertThat(a.sameFile(b)).isTrue();
    assertThat(a.sameFile(c)).isFalse();
    assertThat(a.sameFile(null)).isFalse();
  }

  @Test
  @DisplayName("isStaleComparedTo 优先使用内容哈希，mtime 非唯一证据")
  void isStaleUsesContentHashOverMtime() {
    // 相同哈希但不同 mtime -> 未过期
    SourceFingerprint withHash1 =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CODEX, 100, 1000L, Optional.of("same-hash"));
    SourceFingerprint withHash2 =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CODEX, 100, 9999L, Optional.of("same-hash"));
    assertThat(withHash1.isStaleComparedTo(withHash2)).isFalse();

    // 不同哈希 -> 已过期（即使 mtime 相同）
    SourceFingerprint withDifferentHash =
        new SourceFingerprint(
            "/data/test.jsonl", SourceId.CODEX, 100, 1000L, Optional.of("different-hash"));
    assertThat(withHash1.isStaleComparedTo(withDifferentHash)).isTrue();

    // 无内容哈希时回退到 size+mtime
    SourceFingerprint noHash1 =
        new SourceFingerprint("/data/test.jsonl", SourceId.CODEX, 100, 1000L, Optional.empty());
    SourceFingerprint noHash2 =
        new SourceFingerprint("/data/test.jsonl", SourceId.CODEX, 100, 1000L, Optional.empty());
    assertThat(noHash1.isStaleComparedTo(noHash2)).isFalse();

    SourceFingerprint noHashDifferentSize =
        new SourceFingerprint("/data/test.jsonl", SourceId.CODEX, 200, 1000L, Optional.empty());
    assertThat(noHash1.isStaleComparedTo(noHashDifferentSize)).isTrue();
  }

  @Test
  @DisplayName("null contentHash 参数被规范化为 Optional.empty")
  void nullContentHashNormalized() {
    SourceFingerprint fp = new SourceFingerprint("/test", SourceId.QODER, 0, 0, null);
    assertThat(fp.contentHash()).isEmpty();
  }
}
