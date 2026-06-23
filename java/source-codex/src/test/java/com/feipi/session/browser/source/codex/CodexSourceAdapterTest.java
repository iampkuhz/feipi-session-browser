package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceOutcome;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link CodexSourceAdapter} 单元测试。
 *
 * <p>验证适配器 SPI 各方法在各种输入下的行为，包括源标识、 根目录检查、会话发现、文件指纹和解析。
 */
@DisplayName("CodexSourceAdapter 适配器测试")
class CodexSourceAdapterTest {

  @TempDir Path tempDir;

  private CodexSourceAdapter adapter;

  @BeforeEach
  void setUp() {
    adapter = new CodexSourceAdapter();
  }

  @Nested
  @DisplayName("sourceId")
  class SourceIdTests {

    @Test
    @DisplayName("返回 CODEX")
    void sourceIdReturnsCodex() {
      assertThat(adapter.sourceId()).isEqualTo(SourceId.CODEX);
    }
  }

  @Nested
  @DisplayName("checkRoot")
  class CheckRootTests {

    @Test
    @DisplayName("有效目录返回安全结果")
    void validDirectoryReturnsSafeResult() throws IOException {
      Path root = Files.createDirectory(tempDir.resolve("codex-root"));
      SourceRoot rootResult = adapter.checkRoot(root);

      assertThat(rootResult).isNotNull();
      assertThat(rootResult.rootPath()).isEqualTo(root);
      assertThat(rootResult.isSafe()).isTrue();
    }

    @Test
    @DisplayName("不存在目录返回结果")
    void nonExistingDirectoryReturnsResult() {
      Path nonExisting = tempDir.resolve("does-not-exist");
      SourceRoot rootResult = adapter.checkRoot(nonExisting);

      assertThat(rootResult).isNotNull();
      assertThat(rootResult.rootPath()).isEqualTo(nonExisting);
    }
  }

  @Nested
  @DisplayName("discover")
  class DiscoverTests {

    @Test
    @DisplayName("空目录返回空流")
    void emptyDirectoryReturnsEmptyStream() {
      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream).isNotNull();
      assertThat(stream.isEmpty()).isTrue();
      assertThat(stream.size()).isZero();
    }

    @Test
    @DisplayName("有会话时返回按路径排序的候选项")
    void withSessionsReturnsSortedCandidates() throws IOException {
      // 创建 day-dir/session-dir/session.jsonl 结构
      Path dayB = tempDir.resolve("2024-02-01");
      Path dayA = tempDir.resolve("2024-01-15");

      Path sessionB = dayB.resolve("session-beta");
      Path sessionA = dayA.resolve("session-alpha");
      Files.createDirectories(sessionB);
      Files.createDirectories(sessionA);

      Files.writeString(
          sessionB.resolve("session.jsonl"), "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);
      Files.writeString(
          sessionA.resolve("session.jsonl"), "{\"type\":\"user\"}\n", StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(2);
      List<Candidate> items = stream.orderedItems();
      // 按路径排序，2024-01-15 在前
      assertThat(items.get(0).sessionKey()).startsWith("2024-01-15/");
      assertThat(items.get(1).sessionKey()).startsWith("2024-02-01/");
    }

    @Test
    @DisplayName("候选项包含正确的 sessionKey 和 projectKey")
    void candidateHasCorrectMetadata() throws IOException {
      Path dayDir = tempDir.resolve("2024-03-10");
      Path sessionDir = dayDir.resolve("abc-123");
      Files.createDirectories(sessionDir);
      Files.writeString(
          sessionDir.resolve("session.jsonl"),
          "{\"type\":\"assistant\"}\n",
          StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(1);
      Candidate candidate = stream.orderedItems().get(0);
      assertThat(candidate.sessionKey()).isEqualTo("2024-03-10/abc-123");
      assertThat(candidate.projectKey()).isEqualTo("2024-03-10");
      assertThat(candidate.sourceId()).isEqualTo(SourceId.CODEX);
    }
  }

  @Nested
  @DisplayName("fingerprint")
  class FingerprintTests {

    @Test
    @DisplayName("包含正确的 size、mtime 和 contentHash")
    void containsCorrectSizeMtimeContentHash() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      String content = "{\"type\":\"assistant\",\"message\":\"hello\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);

      assertThat(fp.locator()).isEqualTo(file.toAbsolutePath().toString());
      assertThat(fp.sourceId()).isEqualTo(SourceId.CODEX);
      assertThat(fp.sizeBytes()).isEqualTo(content.getBytes(StandardCharsets.UTF_8).length);
      assertThat(fp.lastModifiedMs()).isGreaterThan(0);
      assertThat(fp.contentHash()).isPresent();
      // SHA-256 哈希为 64 位十六进制字符串
      assertThat(fp.contentHash().get()).hasSize(64);
    }

    @Test
    @DisplayName("不存在的文件返回零值")
    void nonExistingFileReturnsZeroValues() {
      Path nonExisting = tempDir.resolve("missing.jsonl");
      SourceFingerprint fp = adapter.fingerprint(nonExisting);

      assertThat(fp.sourceId()).isEqualTo(SourceId.CODEX);
      assertThat(fp.sizeBytes()).isZero();
      assertThat(fp.lastModifiedMs()).isZero();
      assertThat(fp.contentHash()).isEmpty();
    }

    @Test
    @DisplayName("相同内容产生相同哈希")
    void sameContentProducesSameHash() throws IOException {
      Path file1 = tempDir.resolve("file1.jsonl");
      Path file2 = tempDir.resolve("file2.jsonl");
      String content = "{\"type\":\"test\"}\n";
      Files.writeString(file1, content, StandardCharsets.UTF_8);
      Files.writeString(file2, content, StandardCharsets.UTF_8);

      SourceFingerprint fp1 = adapter.fingerprint(file1);
      SourceFingerprint fp2 = adapter.fingerprint(file2);

      assertThat(fp1.contentHash()).isEqualTo(fp2.contentHash());
    }
  }

  @Nested
  @DisplayName("parse")
  class ParseTests {

    @Test
    @DisplayName("有效 JSONL 返回 success")
    void validJsonlReturnsSuccess() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      String content =
          "{\"type\":\"assistant\",\"message\":\"hello\"}\n"
              + "{\"type\":\"user\",\"message\":\"world\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
      assertThat(result).isInstanceOf(SourceResult.Success.class);
      SourceResult.Success success = (SourceResult.Success) result;
      assertThat(success.candidateCount()).isEqualTo(2);
    }

    @Test
    @DisplayName("不存在的文件返回 skipped")
    void nonExistingFileReturnsSkipped() {
      SourceFingerprint fp =
          new SourceFingerprint(
              tempDir.resolve("missing.jsonl").toAbsolutePath().toString(),
              SourceId.CODEX,
              0,
              0,
              Optional.empty(),
              Optional.empty());
      Candidate candidate = new Candidate(fp, "test/missing", "test", Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SKIPPED);
      assertThat(result).isInstanceOf(SourceResult.Skipped.class);
    }

    @Test
    @DisplayName("损坏 JSONL 返回 success 并带诊断信息")
    void corruptJsonlReturnsSuccessWithDiagnostics() throws IOException {
      Path file = tempDir.resolve("corrupt.jsonl");
      String content =
          "{\"type\":\"assistant\"}\n" + "this is not json at all\n" + "{\"type\":\"user\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/corrupt", "test", Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
      assertThat(result).isInstanceOf(SourceResult.Success.class);
      SourceResult.Success success = (SourceResult.Success) result;
      assertThat(success.candidateCount()).isEqualTo(2);
      assertThat(success.diagnostics()).isNotEmpty();
    }

    @Test
    @DisplayName("空文件返回 success 且事件数为零")
    void emptyFileReturnsSuccessWithZeroEvents() throws IOException {
      Path file = tempDir.resolve("empty.jsonl");
      Files.writeString(file, "", StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/empty", "test", Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
      SourceResult.Success success = (SourceResult.Success) result;
      assertThat(success.candidateCount()).isZero();
    }

    @Test
    @DisplayName("取消信号返回 skipped")
    void cancelledSignalReturnsSkipped() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      Files.writeString(file, "{\"type\":\"test\"}\n", StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", Map.of());

      SourceAdapter.CancellationSignal cancelled = () -> true;
      SourceResult result = adapter.parse(candidate, cancelled);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SKIPPED);
    }
  }
}
