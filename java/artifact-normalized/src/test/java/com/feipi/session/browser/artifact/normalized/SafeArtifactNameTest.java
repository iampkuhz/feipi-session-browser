package com.feipi.session.browser.artifact.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link SafeArtifactName} 路径安全合约测试。 */
@DisplayName("SafeArtifactName 路径安全测试")
class SafeArtifactNameTest {

  @TempDir Path tempDir;

  // ---- sanitize 正常路径测试 ----

  @Test
  @DisplayName("简单 session key 保持不变")
  void simpleKeyUnchanged() {
    assertThat(SafeArtifactName.sanitize("my-session-001")).isEqualTo("my-session-001");
  }

  @Test
  @DisplayName("含空格的 key 保留空格")
  void keyWithSpacesPreserved() {
    assertThat(SafeArtifactName.sanitize("my session")).isEqualTo("my session");
  }

  @Test
  @DisplayName("Unicode key 保留原样")
  void unicodeKeyPreserved() {
    assertThat(SafeArtifactName.sanitize("会话-测试")).isEqualTo("会话-测试");
  }

  // ---- sanitize 路径遍历防护 ----

  @Test
  @DisplayName("路径遍历 ../ 被拒绝")
  void pathTraversalDotDotRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("../../../etc/passwd"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径遍历");
  }

  @Test
  @DisplayName("中间包含 .. 被拒绝")
  void pathTraversalMiddleDotDotRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("foo..bar"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径遍历");
  }

  @Test
  @DisplayName("Unix 路径分隔符 / 被拒绝")
  void unixPathSeparatorRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("foo/bar"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径分隔符");
  }

  @Test
  @DisplayName("Windows 路径分隔符 \\ 被拒绝")
  void windowsPathSeparatorRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("foo\\bar"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("路径分隔符");
  }

  @Test
  @DisplayName("Unix 绝对路径被拒绝")
  void unixAbsolutePathRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("/etc/shadow"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("绝对路径");
  }

  @Test
  @DisplayName("Windows 绝对路径被拒绝")
  void windowsAbsolutePathRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("C:\\Windows\\System32"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("绝对路径");
  }

  @Test
  @DisplayName("null key 被拒绝")
  void nullKeyRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize(null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("空 key 被拒绝")
  void emptyKeyRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize(""))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("空白 key 被拒绝")
  void blankKeyRejected() {
    assertThatThrownBy(() -> SafeArtifactName.sanitize("   "))
        .isInstanceOf(IllegalArgumentException.class);
  }

  // ---- sanitize Windows 保留名 ----

  @Test
  @DisplayName("Windows 保留名 CON 被加前缀")
  void windowsReservedConPrefixed() {
    assertThat(SafeArtifactName.sanitize("CON")).startsWith("_");
  }

  @Test
  @DisplayName("Windows 保留名 NUL 被加前缀")
  void windowsReservedNulPrefixed() {
    assertThat(SafeArtifactName.sanitize("NUL")).startsWith("_");
  }

  @Test
  @DisplayName("Windows 保留名 COM1 被加前缀")
  void windowsReservedCom1Prefixed() {
    assertThat(SafeArtifactName.sanitize("COM1")).startsWith("_");
  }

  @Test
  @DisplayName("Windows 保留名大小写不敏感：con 也被处理")
  void windowsReservedCaseInsensitive() {
    assertThat(SafeArtifactName.sanitize("con")).startsWith("_");
  }

  // ---- sanitize 非法字符 ----

  @Test
  @DisplayName("Windows 非法字符被替换为下划线")
  void illegalCharsReplaced() {
    // 冒号、星号、问号等
    assertThat(SafeArtifactName.sanitize("session:name*here?")).isEqualTo("session_name_here_");
  }

  @Test
  @DisplayName("控制字符被替换")
  void controlCharsReplaced() {
    String input = "sessionname";
    String result = SafeArtifactName.sanitize(input);
    assertThat(result).doesNotContain("");
    assertThat(result).doesNotContain("");
  }

  // ---- sanitize 首尾点号 ----

  @Test
  @DisplayName("前导点号被去除（防止隐藏文件）")
  void leadingDotRemoved() {
    assertThat(SafeArtifactName.sanitize(".hidden-session")).isEqualTo("hidden-session");
  }

  @Test
  @DisplayName("尾部点号被去除")
  void trailingDotRemoved() {
    assertThat(SafeArtifactName.sanitize("session.")).isEqualTo("session");
  }

  // ---- sanitize 长度限制 ----

  @Test
  @DisplayName("超长 key 被截断并附加 hash")
  void longKeyTruncatedWithHash() {
    String longKey = "a".repeat(300);
    String result = SafeArtifactName.sanitize(longKey);
    assertThat(result.length()).isLessThanOrEqualTo(SafeArtifactName.MAX_NAME_LENGTH);
    // 应该包含 hash 后缀
    assertThat(result).contains("-");
  }

  @Test
  @DisplayName("恰好等于最大长度的 key 不被截断")
  void exactMaxLengthNotTruncated() {
    String exactKey = "b".repeat(SafeArtifactName.MAX_NAME_LENGTH);
    String result = SafeArtifactName.sanitize(exactKey);
    assertThat(result.length()).isEqualTo(SafeArtifactName.MAX_NAME_LENGTH);
  }

  // ---- sanitize 不同输入产生不同输出 ----

  @Test
  @DisplayName("不同长 key 截断后通过 hash 区分")
  void differentLongKeysDistinguishedByHash() {
    String key1 = "a".repeat(300) + "1";
    String key2 = "a".repeat(300) + "2";
    String result1 = SafeArtifactName.sanitize(key1);
    String result2 = SafeArtifactName.sanitize(key2);
    assertThat(result1).isNotEqualTo(result2);
  }

  // ---- validateWithinRoot 测试 ----

  @Test
  @DisplayName("正常路径在 root 内：验证通过")
  void normalPathWithinRootPasses() {
    Path target = tempDir.resolve("session.json");
    // 不抛异常即通过
    SafeArtifactName.validateWithinRoot(tempDir, target);
  }

  @Test
  @DisplayName("路径遍历逃逸 root：验证失败")
  void pathTraversalOutOfRootFails() {
    Path target = tempDir.resolve("../../etc/passwd");
    assertThatThrownBy(() -> SafeArtifactName.validateWithinRoot(tempDir, target))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("逃逸");
  }

  @Test
  @DisplayName("symlink 逃逸 root：验证失败")
  void symlinkEscapeOutOfRootFails() throws IOException {
    // 在 tempDir 外创建一个目标文件
    Path outsideDir = tempDir.resolveSibling("outside-dir");
    Files.createDirectories(outsideDir);
    Path outsideFile = outsideDir.resolve("outside.txt");
    Files.writeString(outsideFile, "outside content");

    // 在 tempDir 内创建指向外部文件的 symlink
    Path symlink = tempDir.resolve("escape-link");
    Files.createSymbolicLink(symlink, outsideFile);

    try {
      assertThatThrownBy(() -> SafeArtifactName.validateWithinRoot(tempDir, symlink))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("symlink 逃逸");
    } finally {
      Files.deleteIfExists(symlink);
      Files.deleteIfExists(outsideFile);
      Files.deleteIfExists(outsideDir);
    }
  }

  @Test
  @DisplayName("root 内 symlink：验证通过")
  void symlinkWithinRootPasses() throws IOException {
    // 在 tempDir 内创建目标文件
    Path target = tempDir.resolve("real-file.txt");
    Files.writeString(target, "real content");

    // 在 tempDir 内创建指向内部文件的 symlink
    Path symlink = tempDir.resolve("internal-link");
    Files.createSymbolicLink(symlink, target);

    try {
      // 不抛异常即通过
      SafeArtifactName.validateWithinRoot(tempDir, symlink);
    } finally {
      Files.deleteIfExists(symlink);
      Files.deleteIfExists(target);
    }
  }
}
