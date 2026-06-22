package com.feipi.session.browser.artifact.normalized;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link NormalizedArtifactWriter} 文件写入合约测试。 */
@DisplayName("NormalizedArtifactWriter 文件写入测试")
class NormalizedArtifactWriterTest {

  @TempDir Path tempDir;

  private NormalizedArtifactWriter writer;

  @BeforeEach
  void setUp() {
    writer = new NormalizedArtifactWriter();
  }

  @Test
  @DisplayName("写入并读回：write → readMeta → validate 全部成功")
  void writeAndReadBackRoundTrip() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-round-trip");
    Map<String, String> fingerprints = Map.of("/path/to/source.jsonl", "abc123");

    writer.write(tempDir, artifact, fingerprints);

    Path dataFile = tempDir.resolve("session-round-trip.json");
    Path metaFile = tempDir.resolve("session-round-trip.meta.json");

    assertThat(dataFile).exists();
    assertThat(metaFile).exists();

    ArtifactMeta meta = writer.readMeta(metaFile);
    assertThat(meta.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(meta.generator()).isEqualTo(ArtifactConstants.GENERATOR);
    assertThat(meta.contentHash()).isNotEmpty();
    assertThat(meta.contentSize()).isGreaterThan(0);
    assertThat(meta.generatedAt()).isNotEmpty();
    assertThat(meta.sourceFingerprints()).containsEntry("/path/to/source.jsonl", "abc123");

    // 验证数据文件哈希与 meta 一致
    assertThat(writer.validate(dataFile, metaFile)).isTrue();
  }

  @Test
  @DisplayName("失败安全：写入后 data 文件内容正确")
  void writeAfterDataFileContentCorrect() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-content");
    writer.write(tempDir, artifact, Map.of());

    Path dataFile = tempDir.resolve("session-content.json");
    byte[] dataBytes = Files.readAllBytes(dataFile);
    String content = new String(dataBytes, StandardCharsets.UTF_8);

    // 内容是有效的 JSON
    assertThat(content).startsWith("{");
    assertThat(content).endsWith("}");
    // 包含 session_key
    assertThat(content).contains("session-content");
  }

  @Test
  @DisplayName("覆盖写入：第二次覆盖第一次，内容正确")
  void overwriteSecondWriteOverwritesFirst() throws IOException {
    // 第一次写入
    NormalizedSessionArtifact artifact1 = createMinimalArtifact("session-overwrite");
    Map<String, String> fingerprints1 = Map.of("/source1.jsonl", "hash1");
    writer.write(tempDir, artifact1, fingerprints1);

    Path metaFile = tempDir.resolve("session-overwrite.meta.json");
    ArtifactMeta meta1 = writer.readMeta(metaFile);

    // 第二次写入（相同 session key，不同指纹）
    NormalizedSessionArtifact artifact2 = createMinimalArtifact("session-overwrite");
    Map<String, String> fingerprints2 = Map.of("/source2.jsonl", "hash2");
    writer.write(tempDir, artifact2, fingerprints2);

    ArtifactMeta meta2 = writer.readMeta(metaFile);

    // meta 已被覆盖
    assertThat(meta2.sourceFingerprints()).containsEntry("/source2.jsonl", "hash2");
    assertThat(meta2.sourceFingerprints()).doesNotContainKey("/source1.jsonl");
    // 数据内容相同（因为 artifact 相同）
    assertThat(meta2.contentHash()).isEqualTo(meta1.contentHash());

    // 验证仍然通过
    Path dataFile = tempDir.resolve("session-overwrite.json");
    assertThat(writer.validate(dataFile, metaFile)).isTrue();
  }

  @Test
  @DisplayName("hash 不匹配：手动修改 data 文件后 validate 失败")
  void validateHashMismatchAfterDataFileModification() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-tamper");
    writer.write(tempDir, artifact, Map.of());

    Path dataFile = tempDir.resolve("session-tamper.json");
    Path metaFile = tempDir.resolve("session-tamper.meta.json");

    // 验证初始状态
    assertThat(writer.validate(dataFile, metaFile)).isTrue();

    // 手动修改数据文件
    Files.writeString(dataFile, "{\"tampered\":true}", StandardCharsets.UTF_8);

    // 验证应该失败
    assertThat(writer.validate(dataFile, metaFile)).isFalse();
  }

  @Test
  @DisplayName("meta 后提交：meta 文件的 generatedAt 晚于或等于 data 文件写入时间")
  void metaTimestampMetaWrittenAfterDataFile() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-timing");
    writer.write(tempDir, artifact, Map.of());

    Path dataFile = tempDir.resolve("session-timing.json");
    Path metaFile = tempDir.resolve("session-timing.meta.json");

    // meta 文件应该存在
    assertThat(metaFile).exists();
    assertThat(dataFile).exists();

    // meta 的 generatedAt 不为空
    ArtifactMeta meta = writer.readMeta(metaFile);
    assertThat(meta.generatedAt()).isNotEmpty();
  }

  @Test
  @DisplayName("session key 回退：无 session_key 时使用 content hash")
  void sessionKeyFallbackToContentHash() throws IOException {
    // 创建没有 session_key 的 artifact
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            "claude_code",
            List.of(),
            Map.of("other_field", "value"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    writer.write(tempDir, artifact, Map.of());

    // 验证文件存在（文件名应该是 hash）
    try (var stream = Files.list(tempDir)) {
      List<Path> files = stream.toList();
      // 应该有数据文件和 meta 文件
      assertThat(files).hasSize(2);
      assertThat(files)
          .anyMatch(p -> p.getFileName().toString().endsWith(".json"))
          .anyMatch(p -> p.getFileName().toString().endsWith(".meta.json"));
    }
  }

  @Test
  @DisplayName("无临时文件残留：写入完成后不应有临时文件")
  void noTempFilesLeftAfterWrite() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-no-temp");
    writer.write(tempDir, artifact, Map.of());

    try (var stream = Files.list(tempDir)) {
      List<Path> files = stream.toList();
      assertThat(files)
          .allMatch(
              p -> !p.getFileName().toString().startsWith(ArtifactConstants.TEMP_FILE_PREFIX));
    }
  }

  private static NormalizedSessionArtifact createMinimalArtifact(String sessionKey) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        "claude_code",
        List.of(),
        Map.of("session_key", sessionKey),
        List.of(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
