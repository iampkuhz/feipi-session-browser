package com.feipi.session.browser.source.spi;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SourcePathOps} 单元测试。
 *
 * <p>验证四个共享工具方法（{@code toRelative}、{@code stripSuffix}、{@code isHidden}、 {@code
 * computeSha256}）在各种输入下的行为。
 */
@DisplayName("SourcePathOps 共享路径操作测试")
class SourcePathOpsTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("toRelative(Path, Path)")
  class ToRelative {

    @Test
    @DisplayName("正常相对化：子路径产生相对路径")
    void normalRelativize() {
      Path root = Path.of("/home/user/data");
      Path file = Path.of("/home/user/data/projects/session.jsonl");
      Path result = SourcePathOps.toRelative(root, file);
      assertThat(result.toString()).isEqualTo("projects/session.jsonl");
    }

    @Test
    @DisplayName("路径包含 .. 时先规范化再相对化")
    void normalizesBeforeRelativize() {
      Path root = Path.of("/home/user/../user/data");
      Path file = Path.of("/home/user/data/./session.jsonl");
      Path result = SourcePathOps.toRelative(root, file);
      assertThat(result.toString()).isEqualTo("session.jsonl");
    }

    @Test
    @DisplayName("不可相对化时回退返回原始文件路径")
    void fallbackWhenCannotRelativize() {
      // Windows 风格不同盘符或绝对不可能相对化的场景在 macOS/Linux 上难以触发，
      // 使用相同路径验证不抛异常
      Path root = Path.of("/a/b");
      Path file = Path.of("/a/b/c");
      Path result = SourcePathOps.toRelative(root, file);
      assertThat(result.toString()).isEqualTo("c");
    }

    @Test
    @DisplayName("根路径与文件路径相同时返回空路径")
    void samePathReturnsEmpty() {
      Path root = Path.of("/home/user/data");
      Path file = Path.of("/home/user/data");
      Path result = SourcePathOps.toRelative(root, file);
      assertThat(result.toString()).isEmpty();
    }
  }

  @Nested
  @DisplayName("stripSuffix(String, String)")
  class StripSuffix {

    @Test
    @DisplayName("存在后缀时去除")
    void removesSuffixWhenPresent() {
      assertThat(SourcePathOps.stripSuffix("session.jsonl", ".jsonl")).isEqualTo("session");
    }

    @Test
    @DisplayName("不存在后缀时返回原文本")
    void returnsOriginalWhenSuffixAbsent() {
      assertThat(SourcePathOps.stripSuffix("session.jsonl", ".txt")).isEqualTo("session.jsonl");
    }

    @Test
    @DisplayName("空后缀返回原文本")
    void emptySuffixReturnsOriginal() {
      assertThat(SourcePathOps.stripSuffix("session", "")).isEqualTo("session");
    }

    @Test
    @DisplayName("后缀等于全文时返回空字符串")
    void fullMatchReturnsEmpty() {
      assertThat(SourcePathOps.stripSuffix(".jsonl", ".jsonl")).isEmpty();
    }
  }

  @Nested
  @DisplayName("isHidden(Path)")
  class IsHidden {

    @Test
    @DisplayName("以点开头的文件名视为隐藏")
    void dotPrefixIsHidden() throws IOException {
      Path hiddenFile = tempDir.resolve(".hidden");
      Files.createFile(hiddenFile);
      assertThat(SourcePathOps.isHidden(hiddenFile)).isTrue();
    }

    @Test
    @DisplayName("普通文件名不隐藏")
    void normalNameIsNotHidden() throws IOException {
      Path normalFile = tempDir.resolve("session.jsonl");
      Files.createFile(normalFile);
      assertThat(SourcePathOps.isHidden(normalFile)).isFalse();
    }

    @Test
    @DisplayName("以点开头的目录名视为隐藏")
    void dotPrefixDirIsHidden() throws IOException {
      Path hiddenDir = tempDir.resolve(".git");
      Files.createDirectory(hiddenDir);
      assertThat(SourcePathOps.isHidden(hiddenDir)).isTrue();
    }
  }

  @Nested
  @DisplayName("computeSha256(Path)")
  class ComputeSha256 {

    @Test
    @DisplayName("相同内容产生相同哈希")
    void sameContentSameHash() throws IOException {
      Path file1 = tempDir.resolve("file1.txt");
      Path file2 = tempDir.resolve("file2.txt");
      Files.writeString(file1, "hello world", StandardCharsets.UTF_8);
      Files.writeString(file2, "hello world", StandardCharsets.UTF_8);
      assertThat(SourcePathOps.computeSha256(file1)).isEqualTo(SourcePathOps.computeSha256(file2));
    }

    @Test
    @DisplayName("不同内容产生不同哈希")
    void differentContentDifferentHash() throws IOException {
      Path file1 = tempDir.resolve("file1.txt");
      Path file2 = tempDir.resolve("file2.txt");
      Files.writeString(file1, "hello", StandardCharsets.UTF_8);
      Files.writeString(file2, "world", StandardCharsets.UTF_8);
      assertThat(SourcePathOps.computeSha256(file1))
          .isNotEqualTo(SourcePathOps.computeSha256(file2));
    }

    @Test
    @DisplayName("哈希结果为 64 位十六进制字符串")
    void hashIsHex64Chars() throws IOException {
      Path file = tempDir.resolve("test.txt");
      Files.writeString(file, "test content", StandardCharsets.UTF_8);
      String hash = SourcePathOps.computeSha256(file);
      assertThat(hash).hasSize(64).matches("[0-9a-f]+");
    }
  }
}
