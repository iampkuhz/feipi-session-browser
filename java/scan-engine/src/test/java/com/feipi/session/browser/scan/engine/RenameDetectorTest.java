package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link RenameDetector} 测试。
 *
 * <p>覆盖重命名检测：文件在新位置找到、根目录不可访问、session_id 提取。
 */
class RenameDetectorTest {

  @TempDir Path tempDir;

  @Test
  void detectRenameFindsFileInDifferentProject() throws Exception {
    Path root = tempDir.resolve("root");
    Path projectA = root.resolve("project-A");
    Path projectB = root.resolve("project-B");
    Files.createDirectories(projectA);
    Files.createDirectories(projectB);

    // 文件在 project-B
    Path sourceFile = projectB.resolve("session-123.jsonl");
    Files.writeString(sourceFile, "{\"data\": true}");

    var result = RenameDetector.detectRename(new TestAdapter(), root, "claude_code:session-123");

    assertThat(result).isPresent();
    assertThat(result.get().newFilePath()).isEqualTo(sourceFile.toString());
  }

  @Test
  void detectRenameReturnsEmptyWhenNoMatch() throws Exception {
    Path root = tempDir.resolve("root");
    Files.createDirectories(root);

    var result =
        RenameDetector.detectRename(new TestAdapter(), root, "claude_code:nonexistent-session");

    assertThat(result).isEmpty();
  }

  @Test
  void detectRenameReturnsEmptyForNonExistentRoot() {
    Path nonExistent = tempDir.resolve("does-not-exist");

    var result =
        RenameDetector.detectRename(new TestAdapter(), nonExistent, "claude_code:session-123");

    assertThat(result).isEmpty();
  }

  @Test
  void isRootAccessibleReturnsTrueForExistingDirectory() throws Exception {
    Path root = tempDir.resolve("accessible-root");
    Files.createDirectories(root);

    boolean accessible = RenameDetector.isRootAccessible(new TestAdapter(), root);
    assertThat(accessible).isTrue();
  }

  @Test
  void isRootAccessibleReturnsFalseForNonExistentDirectory() {
    Path nonExistent = tempDir.resolve("non-existent");

    boolean accessible = RenameDetector.isRootAccessible(new TestAdapter(), nonExistent);
    assertThat(accessible).isFalse();
  }

  @Test
  void extractSessionIdFromQualifiedKey() {
    assertThat(RenameDetector.extractSessionId("claude_code:uuid-123")).isEqualTo("uuid-123");
    assertThat(RenameDetector.extractSessionId("codex:abc")).isEqualTo("abc");
  }

  @Test
  void extractSessionIdFromUnqualifiedKey() {
    assertThat(RenameDetector.extractSessionId("plain-key")).isEqualTo("plain-key");
  }

  @Test
  void detectRenamePrefersExactMatch() throws Exception {
    Path root = tempDir.resolve("root");
    Path projectDir = root.resolve("project");
    Files.createDirectories(projectDir);

    // 创建两个文件：一个精确匹配，一个部分匹配
    Path exactMatch = projectDir.resolve("session-123.jsonl");
    Path partialMatch = projectDir.resolve("session-123-extra.jsonl");
    Files.writeString(exactMatch, "{\"exact\": true}");
    Files.writeString(partialMatch, "{\"partial\": true}");

    var result = RenameDetector.detectRename(new TestAdapter(), root, "claude_code:session-123");

    assertThat(result).isPresent();
    // 精确匹配优先（按文件名排序）
    assertThat(result.get().newFilePath()).contains("session-123");
  }

  // ===== 测试用适配器 =====

  private static class TestAdapter implements SourceAdapter {
    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }
}
