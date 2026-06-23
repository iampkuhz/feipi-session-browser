package com.feipi.session.browser.source.qoder;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParsedRecord;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
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
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link QoderSourceAdapter} 单元测试。
 *
 * <p>验证适配器 SPI 各方法在各种输入下的行为，包括源标识、 根目录检查、会话发现（含 cache/projects/）、 文件指纹和解析。
 */
@DisplayName("QoderSourceAdapter 适配器测试")
class QoderSourceAdapterTest {

  @TempDir Path tempDir;

  private QoderSourceAdapter adapter;

  @BeforeEach
  void setUp() {
    adapter = new QoderSourceAdapter();
  }

  @Nested
  @DisplayName("sourceId")
  class SourceIdTests {

    @Test
    @DisplayName("返回 QODER")
    void sourceIdReturnsQoder() {
      assertThat(adapter.sourceId()).isEqualTo(SourceId.QODER);
    }
  }

  @Nested
  @DisplayName("checkRoot")
  class CheckRootTests {

    @Test
    @DisplayName("有效目录返回安全结果")
    void validDirectoryReturnsSafeResult() throws IOException {
      Path root = Files.createDirectory(tempDir.resolve("qoder-root"));
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
      Path projects = tempDir.resolve("projects");
      Path projectB = projects.resolve("project-b");
      Path projectA = projects.resolve("project-a");
      Files.createDirectories(projectA);
      Files.createDirectories(projectB);

      Path sessionB = projectB.resolve("session-2.jsonl");
      Path sessionA = projectA.resolve("session-1.jsonl");
      Files.writeString(sessionB, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);
      Files.writeString(sessionA, "{\"type\":\"user\"}\n", StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(2);
      List<Candidate> items = stream.orderedItems();
      assertThat(items.get(0).fingerprint().locator())
          .isLessThan(items.get(1).fingerprint().locator());
    }

    @Test
    @DisplayName("候选项包含正确的 sessionKey 和 projectKey")
    void candidateHasCorrectMetadata() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);
      Path sessionFile = projectDir.resolve("abc-123.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(1);
      Candidate candidate = stream.orderedItems().get(0);
      assertThat(candidate.sessionKey()).isEqualTo("my-project/abc-123");
      assertThat(candidate.projectKey()).isEqualTo("my-project");
      assertThat(candidate.sourceId()).isEqualTo(SourceId.QODER);
    }

    @Test
    @DisplayName("cache/projects/ 目录中的会话也被发现")
    void cacheProjectsSessionsAreDiscovered() throws IOException {
      Path cacheProjects = tempDir.resolve("cache").resolve("projects");
      Path cacheProject = cacheProjects.resolve("cached-project");
      Files.createDirectories(cacheProject);
      Path sessionFile = cacheProject.resolve("cached-session.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(1);
      Candidate candidate = stream.orderedItems().get(0);
      assertThat(candidate.sessionKey()).isEqualTo("cached-project/cached-session");
      assertThat(candidate.sourceId()).isEqualTo(SourceId.QODER);
    }

    @Test
    @DisplayName("URL 编码的项目目录名被解码为 projectKey")
    void urlEncodedProjectKeyDecoded() throws IOException {
      Path projects = tempDir.resolve("projects");
      // URL 编码的 "home/user/project" 形式
      Path projectDir = projects.resolve("home%2Fuser%2Fproject");
      Files.createDirectories(projectDir);
      Path sessionFile = projectDir.resolve("session.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      BoundedStream<Candidate> stream = adapter.discover(tempDir);

      assertThat(stream.size()).isEqualTo(1);
      Candidate candidate = stream.orderedItems().get(0);
      assertThat(candidate.projectKey()).isEqualTo("home/user/project");
      assertThat(candidate.sessionKey()).isEqualTo("home%2Fuser%2Fproject/session");
    }
  }

  @Nested
  @DisplayName("fingerprint")
  class FingerprintTests {

    @Test
    @DisplayName("包含正确的 size、mtime 和 contentHash")
    void containsCorrectSizeMtimeContentHash() throws IOException {
      Path file = tempDir.resolve("test.jsonl");
      String content = "{\"type\":\"assistant\",\"message\":\"hello\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);

      assertThat(fp.locator()).isEqualTo(file.toAbsolutePath().toString());
      assertThat(fp.sourceId()).isEqualTo(SourceId.QODER);
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

      assertThat(fp.sourceId()).isEqualTo(SourceId.QODER);
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
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

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
              SourceId.QODER,
              0,
              0,
              Optional.empty(),
              Optional.empty());
      Candidate candidate = new Candidate(fp, "test/missing", "test", java.util.Map.of());

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
      Candidate candidate = new Candidate(fp, "test/corrupt", "test", java.util.Map.of());

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
      Candidate candidate = new Candidate(fp, "test/empty", "test", java.util.Map.of());

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
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceAdapter.CancellationSignal cancelled = () -> true;
      SourceResult result = adapter.parse(candidate, cancelled);

      assertThat(result.outcome()).isEqualTo(SourceOutcome.SKIPPED);
    }

    @Test
    @DisplayName("parse 返回与事件数量一致的 ParsedRecord 列表")
    void parseReturnsMatchingParsedRecords() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      String content =
          "{\"type\":\"user\",\"message\":\"hello\"}\n"
              + "{\"type\":\"assistant\",\"message\":\"world\"}\n"
              + "{\"type\":\"user\",\"message\":\"third\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result).isInstanceOf(SourceResult.Success.class);
      SourceResult.Success success = (SourceResult.Success) result;
      List<ParsedRecord> records = success.records();
      assertThat(records).hasSize(3);
      // 验证每条 record 的 locator 包含文件路径和事件序号
      assertThat(records.get(0).locator()).endsWith("#event[0]");
      assertThat(records.get(1).locator()).endsWith("#event[1]");
      assertThat(records.get(2).locator()).endsWith("#event[2]");
    }

    @Test
    @DisplayName("ParsedRecord 的 eventType 与源事件 type 字段对应")
    void parsedRecordEventTypeMatchesSource() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      String content =
          "{\"type\":\"user\",\"message\":\"hello\"}\n"
              + "{\"type\":\"assistant\",\"message\":\"world\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);
      SourceResult.Success success = (SourceResult.Success) result;

      QoderParsedRecord r0 = (QoderParsedRecord) success.records().get(0);
      QoderParsedRecord r1 = (QoderParsedRecord) success.records().get(1);
      assertThat(r0.eventType()).isEqualTo("user");
      assertThat(r1.eventType()).isEqualTo("assistant");
    }

    @Test
    @DisplayName("缺少 type 字段的事件产生 UNKNOWN_BLOCK_TYPE 诊断")
    void missingTypeFieldProducesDiagnostic() throws IOException {
      Path file = tempDir.resolve("session.jsonl");
      String content =
          "{\"type\":\"user\",\"message\":\"hello\"}\n"
              + "{\"message\":\"no type here\"}\n"
              + "{\"type\":\"assistant\",\"message\":\"world\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result).isInstanceOf(SourceResult.Success.class);
      SourceResult.Success success = (SourceResult.Success) result;
      // 验证 UNKNOWN_BLOCK_TYPE 诊断存在
      List<SourceDiagnostic> unknownDiags =
          success.diagnostics().stream()
              .filter(d -> "UNKNOWN_BLOCK_TYPE".equals(d.code()))
              .toList();
      assertThat(unknownDiags).hasSize(1);
      assertThat(unknownDiags.get(0).message()).contains("missing 'type' field");
      // 验证仍然产生了 3 条 record（不丢弃事件）
      assertThat(success.records()).hasSize(3);
    }

    @Test
    @DisplayName("cache 格式事件（role 字段）产生 CACHE_FORMAT_ROLE 诊断并使用 role 值作为 eventType")
    void cacheFormatRoleFieldProducesDiagnostic() throws IOException {
      Path file = tempDir.resolve("cache-session.jsonl");
      String content =
          "{\"role\":\"user\",\"message\":\"hello\"}\n"
              + "{\"role\":\"assistant\",\"message\":\"world\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);

      assertThat(result).isInstanceOf(SourceResult.Success.class);
      SourceResult.Success success = (SourceResult.Success) result;
      // 验证 CACHE_FORMAT_ROLE 诊断存在
      List<SourceDiagnostic> cacheDiags =
          success.diagnostics().stream().filter(d -> "CACHE_FORMAT_ROLE".equals(d.code())).toList();
      assertThat(cacheDiags).hasSize(2);
      // 验证 eventType 使用 role 值
      QoderParsedRecord r0 = (QoderParsedRecord) success.records().get(0);
      QoderParsedRecord r1 = (QoderParsedRecord) success.records().get(1);
      assertThat(r0.eventType()).isEqualTo("user");
      assertThat(r1.eventType()).isEqualTo("assistant");
    }

    @Test
    @DisplayName("混合 schema 事件正确处理：type 优先于 role")
    void typeFieldTakesPrecedenceOverRole() throws IOException {
      Path file = tempDir.resolve("mixed.jsonl");
      // 第一个事件有 type 和 role，type 优先
      String content =
          "{\"type\":\"assistant\",\"role\":\"user\",\"message\":\"hello\"}\n"
              + "{\"role\":\"user\",\"message\":\"cache format\"}\n";
      Files.writeString(file, content, StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/session", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);
      SourceResult.Success success = (SourceResult.Success) result;

      // 第一个事件 type=assistant 优先
      QoderParsedRecord r0 = (QoderParsedRecord) success.records().get(0);
      assertThat(r0.eventType()).isEqualTo("assistant");
      // 第二个事件没有 type，使用 role=user，产生 CACHE_FORMAT_ROLE 诊断
      QoderParsedRecord r1 = (QoderParsedRecord) success.records().get(1);
      assertThat(r1.eventType()).isEqualTo("user");
    }

    @Test
    @DisplayName("空文件返回空 records 列表")
    void emptyFileReturnsEmptyRecords() throws IOException {
      Path file = tempDir.resolve("empty.jsonl");
      Files.writeString(file, "", StandardCharsets.UTF_8);

      SourceFingerprint fp = adapter.fingerprint(file);
      Candidate candidate = new Candidate(fp, "test/empty", "test", java.util.Map.of());

      SourceResult result = adapter.parse(candidate, null);
      SourceResult.Success success = (SourceResult.Success) result;
      assertThat(success.records()).isEmpty();
    }
  }
}
