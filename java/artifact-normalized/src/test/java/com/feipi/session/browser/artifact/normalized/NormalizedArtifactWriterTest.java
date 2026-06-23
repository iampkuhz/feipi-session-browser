package com.feipi.session.browser.artifact.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link NormalizedArtifactWriter} 文件写入合约测试。 */
@DisplayName("NormalizedArtifactWriter 文件写入测试")
class NormalizedArtifactWriterTest {

  @TempDir Path tempDir;

  /** 固定时钟，用于确定性测试。 */
  private static final Clock FIXED_CLOCK =
      Clock.fixed(Instant.parse("2024-06-15T10:30:00Z"), ZoneOffset.UTC);

  private NormalizedArtifactWriter writer;

  @BeforeEach
  void setUp() {
    writer = new NormalizedArtifactWriter(FIXED_CLOCK);
  }

  @Test
  @DisplayName("写入并读回：write → readMeta → validate 全部成功")
  void writeAndReadBackRoundTrip() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-round-trip");
    Map<String, String> fingerprints = Map.of("/path/to/source.jsonl", "abc123");

    WriteResult result = writer.write(tempDir, artifact, fingerprints);

    assertThat(result.status()).isEqualTo("SUCCESS");
    assertThat(result.dataPath()).exists();
    assertThat(result.metaPath()).exists();
    assertThat(result.contentHash()).isNotEmpty();
    assertThat(result.contentSize()).isGreaterThan(0);

    Path dataFile = result.dataPath();
    Path metaFile = result.metaPath();

    ArtifactMeta meta = writer.readMeta(metaFile);
    assertThat(meta.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(meta.generator()).isEqualTo(ArtifactConstants.GENERATOR);
    assertThat(meta.contentHash()).isEqualTo(result.contentHash());
    assertThat(meta.contentSize()).isEqualTo(result.contentSize());
    assertThat(meta.generatedAt()).isEqualTo("2024-06-15T10:30:00Z");
    assertThat(meta.sourceFingerprints()).containsEntry("/path/to/source.jsonl", "abc123");

    // 验证数据文件哈希与 meta 一致
    assertThat(writer.validate(dataFile, metaFile)).isTrue();
  }

  @Test
  @DisplayName("WriteResult 包含正确的 dataPath 和 metaPath")
  void writeResultContainsCorrectPaths() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-paths");
    WriteResult result = writer.write(tempDir, artifact, Map.of());

    assertThat(result.dataPath().getFileName().toString()).isEqualTo("session-paths.json");
    assertThat(result.metaPath().getFileName().toString()).isEqualTo("session-paths.meta.json");
    assertThat(result.dataPath().isAbsolute()).isTrue();
    assertThat(result.metaPath().isAbsolute()).isTrue();
  }

  @Test
  @DisplayName("WriteResult 的 contentHash 与 validate 一致")
  void writeResultHashConsistentWithValidate() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-hash-consistency");
    WriteResult result = writer.write(tempDir, artifact, Map.of());

    assertThat(writer.validate(result.dataPath(), result.metaPath())).isTrue();
    assertThat(result.contentHash()).hasSize(64); // SHA-256 hex 长度
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
    WriteResult result = writer.write(tempDir, createMinimalArtifact("session-tamper"), Map.of());

    Path dataFile = result.dataPath();
    Path metaFile = result.metaPath();

    // 验证初始状态
    assertThat(writer.validate(dataFile, metaFile)).isTrue();

    // 手动修改数据文件
    Files.writeString(dataFile, "{\"tampered\":true}", StandardCharsets.UTF_8);

    // 验证应该失败
    assertThat(writer.validate(dataFile, metaFile)).isFalse();
  }

  @Test
  @DisplayName("validate：meta 不存在时返回 false（中间状态不被视为有效）")
  void validateReturnsFalseWhenMetaMissing() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-no-meta");
    WriteResult result = writer.write(tempDir, artifact, Map.of());

    // 删除 meta 文件模拟中间状态
    Files.delete(result.metaPath());

    assertThat(writer.validate(result.dataPath(), result.metaPath())).isFalse();
  }

  @Test
  @DisplayName("validate：data 不存在时返回 false")
  void validateReturnsFalseWhenDataMissing() throws IOException {
    WriteResult result = writer.write(tempDir, createMinimalArtifact("session-no-data"), Map.of());

    // 删除 data 文件
    Files.delete(result.dataPath());

    assertThat(writer.validate(result.dataPath(), result.metaPath())).isFalse();
  }

  @Test
  @DisplayName("meta 后提交：meta 的 generatedAt 使用注入 clock")
  void metaTimestampUsesInjectedClock() throws IOException {
    WriteResult result = writer.write(tempDir, createMinimalArtifact("session-timing"), Map.of());

    ArtifactMeta meta = writer.readMeta(result.metaPath());
    // 使用固定时钟，generatedAt 应该是确定性的
    assertThat(meta.generatedAt()).isEqualTo("2024-06-15T10:30:00Z");
  }

  @Test
  @DisplayName("确定性：固定 clock 下两次写入产生相同 meta 内容（除时间戳外）")
  void deterministicWithFixedClock() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-deterministic");

    WriteResult result1 = writer.write(tempDir, artifact, Map.of());
    byte[] metaBytes1 = Files.readAllBytes(result1.metaPath());

    WriteResult result2 = writer.write(tempDir, artifact, Map.of());
    byte[] metaBytes2 = Files.readAllBytes(result2.metaPath());

    // 使用固定 clock，两次 meta 应该完全相同
    assertThat(metaBytes1).isEqualTo(metaBytes2);
    // content hash 也应该相同
    assertThat(result1.contentHash()).isEqualTo(result2.contentHash());
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

    WriteResult result = writer.write(tempDir, artifact, Map.of());

    // 验证文件存在（文件名应该是 hash）
    assertThat(result.dataPath()).exists();
    assertThat(result.metaPath()).exists();
    assertThat(result.dataPath().getFileName().toString()).endsWith(".json");
    assertThat(result.metaPath().getFileName().toString()).endsWith(".meta.json");
  }

  @Test
  @DisplayName("无临时文件残留：写入完成后不应有临时文件")
  void noTempFilesLeftAfterWrite() throws IOException {
    writer.write(tempDir, createMinimalArtifact("session-no-temp"), Map.of());

    try (var stream = Files.list(tempDir)) {
      List<Path> files = stream.toList();
      assertThat(files)
          .allMatch(
              p -> !p.getFileName().toString().startsWith(ArtifactConstants.TEMP_FILE_PREFIX));
    }
  }

  @Test
  @DisplayName("路径遍历防护：session key 含 ../ 被拒绝")
  void pathTraversalRejected() {
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            "claude_code",
            List.of(),
            Map.of("session_key", "../../../etc/passwd"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    assertThatThrownBy(() -> writer.write(tempDir, artifact, Map.of()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径遍历");
  }

  @Test
  @DisplayName("路径遍历防护：session key 含 / 被拒绝")
  void pathSeparatorRejected() {
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            "claude_code",
            List.of(),
            Map.of("session_key", "foo/bar"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    assertThatThrownBy(() -> writer.write(tempDir, artifact, Map.of()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径分隔符");
  }

  @Test
  @DisplayName("路径遍历防护：绝对路径 session key 被拒绝")
  void absolutePathRejected() {
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            "claude_code",
            List.of(),
            Map.of("session_key", "/etc/shadow"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    assertThatThrownBy(() -> writer.write(tempDir, artifact, Map.of()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("绝对路径");
  }

  @Test
  @DisplayName("source fingerprint 脱敏：home 路径被替换为 ~")
  void sourceFingerprintsSanitizeHomePath() throws IOException {
    String homePath = System.getProperty("user.home");
    if (homePath == null || homePath.isEmpty()) {
      return; // 无法测试
    }

    NormalizedSessionArtifact artifact = createMinimalArtifact("session-fingerprint");
    Map<String, String> fingerprints =
        Map.of(homePath + "/.claude/projects/test/session.jsonl", "hash1");

    WriteResult result = writer.write(tempDir, artifact, fingerprints);
    ArtifactMeta meta = writer.readMeta(result.metaPath());

    // home 路径应被替换为 ~
    assertThat(meta.sourceFingerprints()).containsKey("~/.claude/projects/test/session.jsonl");
    assertThat(meta.sourceFingerprints()).doesNotContainKey(homePath);
  }

  @Test
  @DisplayName("source fingerprint 不脱敏非 home 路径")
  void sourceFingerprintsKeepNonHomePaths() throws IOException {
    NormalizedSessionArtifact artifact = createMinimalArtifact("session-fp-keep");
    Map<String, String> fingerprints = Map.of("/shared/data/session.jsonl", "hash1");

    WriteResult result = writer.write(tempDir, artifact, fingerprints);
    ArtifactMeta meta = writer.readMeta(result.metaPath());

    assertThat(meta.sourceFingerprints()).containsEntry("/shared/data/session.jsonl", "hash1");
  }

  @Test
  @DisplayName("并发安全：不同 key 可以并行写入")
  void concurrentWritesDifferentKeys() throws Exception {
    int threadCount = 4;
    ExecutorService executor = Executors.newFixedThreadPool(threadCount);
    CountDownLatch startLatch = new CountDownLatch(1);
    AtomicInteger successCount = new AtomicInteger(0);

    try {
      List<Future<?>> futures =
          List.of(
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("concurrent-key-a"), Map.of());
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      throw new RuntimeException(e);
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("concurrent-key-b"), Map.of());
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      throw new RuntimeException(e);
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("concurrent-key-c"), Map.of());
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      throw new RuntimeException(e);
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("concurrent-key-d"), Map.of());
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      throw new RuntimeException(e);
                    }
                  }));

      // 同时释放所有线程
      startLatch.countDown();

      for (Future<?> f : futures) {
        f.get(10, TimeUnit.SECONDS);
      }

      assertThat(successCount.get()).isEqualTo(threadCount);

      // 验证所有文件都已正确写入
      assertThat(
              writer.validate(
                  tempDir.resolve("concurrent-key-a.json"),
                  tempDir.resolve("concurrent-key-a.meta.json")))
          .isTrue();
      assertThat(
              writer.validate(
                  tempDir.resolve("concurrent-key-b.json"),
                  tempDir.resolve("concurrent-key-b.meta.json")))
          .isTrue();
      assertThat(
              writer.validate(
                  tempDir.resolve("concurrent-key-c.json"),
                  tempDir.resolve("concurrent-key-c.meta.json")))
          .isTrue();
      assertThat(
              writer.validate(
                  tempDir.resolve("concurrent-key-d.json"),
                  tempDir.resolve("concurrent-key-d.meta.json")))
          .isTrue();
    } finally {
      executor.shutdownNow();
    }
  }

  @Test
  @DisplayName("并发安全：同 key 并发写入互斥，最终状态一致")
  void concurrentWritesSameKeyMutualExclusion() throws Exception {
    int threadCount = 4;
    ExecutorService executor = Executors.newFixedThreadPool(threadCount);
    CountDownLatch startLatch = new CountDownLatch(1);
    AtomicInteger successCount = new AtomicInteger(0);
    AtomicInteger errorCount = new AtomicInteger(0);

    try {
      List<Future<?>> futures =
          List.of(
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("same-key"), Map.of("fp", "v1"));
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      errorCount.incrementAndGet();
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("same-key"), Map.of("fp", "v2"));
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      errorCount.incrementAndGet();
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("same-key"), Map.of("fp", "v3"));
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      errorCount.incrementAndGet();
                    }
                  }),
              executor.submit(
                  () -> {
                    try {
                      startLatch.await();
                      writer.write(tempDir, createMinimalArtifact("same-key"), Map.of("fp", "v4"));
                      successCount.incrementAndGet();
                    } catch (Exception e) {
                      errorCount.incrementAndGet();
                    }
                  }));

      startLatch.countDown();

      for (Future<?> f : futures) {
        f.get(10, TimeUnit.SECONDS);
      }

      // 所有写入都应成功（互斥串行执行）
      assertThat(successCount.get()).isEqualTo(threadCount);

      // 最终状态必须一致（hash 与 size 匹配）
      assertThat(
              writer.validate(
                  tempDir.resolve("same-key.json"), tempDir.resolve("same-key.meta.json")))
          .isTrue();
    } finally {
      executor.shutdownNow();
    }
  }

  @Test
  @DisplayName("默认构造器：使用系统时钟，generatedAt 不为空")
  void defaultConstructorUsesSystemClock() throws IOException {
    NormalizedArtifactWriter systemClockWriter = new NormalizedArtifactWriter();
    WriteResult result =
        systemClockWriter.write(tempDir, createMinimalArtifact("session-system-clock"), Map.of());

    ArtifactMeta meta = writer.readMeta(result.metaPath());
    assertThat(meta.generatedAt()).isNotEmpty();
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
