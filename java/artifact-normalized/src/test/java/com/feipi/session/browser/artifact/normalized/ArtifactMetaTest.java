package com.feipi.session.browser.artifact.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link ArtifactMeta} 不可变 record 合约测试。 */
@DisplayName("ArtifactMeta record 不变量测试")
class ArtifactMetaTest {

  @Test
  @DisplayName("record 访问器返回正确值")
  void accessorsReturnCorrectValues() {
    ArtifactMeta meta =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            "abcdef1234567890",
            1024L,
            "2024-01-01T00:00:00Z",
            Map.of("/path/to/file.jsonl", "hash1"));

    assertThat(meta.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(meta.generator()).isEqualTo(ArtifactConstants.GENERATOR);
    assertThat(meta.contentHash()).isEqualTo("abcdef1234567890");
    assertThat(meta.contentSize()).isEqualTo(1024L);
    assertThat(meta.generatedAt()).isEqualTo("2024-01-01T00:00:00Z");
    assertThat(meta.sourceFingerprints()).containsEntry("/path/to/file.jsonl", "hash1");
  }

  @Test
  @DisplayName("record 相等性：相同内容的两个实例相等")
  void equalitySameContentInstancesAreEqual() {
    ArtifactMeta a =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            "hash123",
            512L,
            "2024-01-01T00:00:00Z",
            Map.of());
    ArtifactMeta b =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            "hash123",
            512L,
            "2024-01-01T00:00:00Z",
            Map.of());

    assertThat(a).isEqualTo(b);
    assertThat(a.hashCode()).isEqualTo(b.hashCode());
  }

  @Test
  @DisplayName("null schemaVersion 抛出 NullPointerException")
  void nullSchemaVersionThrowsNpe() {
    assertThatThrownBy(
            () ->
                new ArtifactMeta(
                    null,
                    ArtifactConstants.GENERATOR,
                    "hash",
                    0L,
                    "2024-01-01T00:00:00Z",
                    Map.of()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null generator 抛出 NullPointerException")
  void nullGeneratorThrowsNpe() {
    assertThatThrownBy(
            () ->
                new ArtifactMeta(
                    NormalizedConstants.SCHEMA_VERSION,
                    null,
                    "hash",
                    0L,
                    "2024-01-01T00:00:00Z",
                    Map.of()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null contentHash 抛出 NullPointerException")
  void nullContentHashThrowsNpe() {
    assertThatThrownBy(
            () ->
                new ArtifactMeta(
                    NormalizedConstants.SCHEMA_VERSION,
                    ArtifactConstants.GENERATOR,
                    null,
                    0L,
                    "2024-01-01T00:00:00Z",
                    Map.of()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("负数 contentSize 抛出 IllegalArgumentException")
  void negativeContentSizeThrowsIae() {
    assertThatThrownBy(
            () ->
                new ArtifactMeta(
                    NormalizedConstants.SCHEMA_VERSION,
                    ArtifactConstants.GENERATOR,
                    "hash",
                    -1L,
                    "2024-01-01T00:00:00Z",
                    Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("null sourceFingerprints 被规范化为空 map")
  void nullSourceFingerprintsNormalizedToEmptyMap() {
    ArtifactMeta meta =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            "hash",
            0L,
            "2024-01-01T00:00:00Z",
            null);
    assertThat(meta.sourceFingerprints()).isEmpty();
  }

  @Test
  @DisplayName("SHA-256 hash 正确性：NormalizedArtifactWriter.sha256Hex 计算正确")
  void sha256ComputedCorrectly() {
    // SHA-256 测试向量：验证已知字符串的摘要计算
    byte[] input = "hello".getBytes(StandardCharsets.UTF_8);
    String hash = NormalizedArtifactWriter.sha256Hex(input);
    // 预期摘要值
    assertThat(hash).isEqualTo("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  }

  @Test
  @DisplayName("SHA-256 hash：空输入")
  void sha256EmptyInput() {
    // SHA-256 测试向量：空输入的预期摘要
    byte[] input = new byte[0];
    String hash = NormalizedArtifactWriter.sha256Hex(input);
    // 预期摘要值
    assertThat(hash).isEqualTo("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  }

  @Test
  @DisplayName("sourceFingerprints 不可变：修改副本不影响 record")
  void sourceFingerprintsImmutable() {
    Map<String, String> original = Map.of("key1", "value1");
    ArtifactMeta meta =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            "hash",
            0L,
            "2024-01-01T00:00:00Z",
            original);

    // Map.copyOf 产生不可变 map
    assertThatThrownBy(() -> meta.sourceFingerprints().put("key2", "value2"))
        .isInstanceOf(UnsupportedOperationException.class);
  }
}
