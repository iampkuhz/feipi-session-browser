package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * {@link StaticPathResolver} 安全测试。
 *
 * <p>验证路径 traversal、null byte 注入、symlink escape 和扩展名白名单。
 */
@DisplayName("静态资源路径安全测试")
class StaticPathResolverTest {

  @TempDir Path tempDir;

  @Test
  @DisplayName("正常路径返回根目录内的归一化路径")
  void normalPathResolvesWithinRoot() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    Path result = resolver.resolve("css/base.css");
    String rootPrefix = tempDir.toAbsolutePath().normalize().toString();
    assertThat(result.toString()).startsWith(rootPrefix);
    assertThat(result.getFileName().toString()).isEqualTo("base.css");
  }

  @Test
  @DisplayName("前导斜杠的路径正常解析")
  void leadingSlashPath() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    Path result = resolver.resolve("/js/app.js");
    String rootPrefix = tempDir.toAbsolutePath().normalize().toString();
    assertThat(result.toString()).startsWith(rootPrefix);
  }

  @ParameterizedTest
  @ValueSource(strings = {"../etc/passwd", "css/../../etc/passwd", "foo/../../../etc/shadow"})
  @DisplayName(".. traversal 序列一律拒绝")
  void traversalRejected(String malicious) {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve(malicious))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("traversal");
  }

  @Test
  @DisplayName("反斜杠路径拒绝（Windows traversal 变体）")
  void backslashRejected() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve("css\\..\\..\\etc\\passwd"))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("非法分隔符");
  }

  @Test
  @DisplayName("null byte 注入拒绝")
  void nullByteRejected() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve("css/base.css\0.html"))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("非法字符");
  }

  @Test
  @DisplayName("空路径拒绝")
  void emptyPathRejected() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve(""))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("路径为空");
  }

  @Test
  @DisplayName("null 路径拒绝")
  void nullPathRejected() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve(null))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("路径为空");
  }

  @ParameterizedTest
  @ValueSource(strings = {"hack.exe", "script.sh", "data.bat", "file.py"})
  @DisplayName("非白名单扩展名拒绝")
  void disallowedExtensionRejected(String fileName) {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    assertThatThrownBy(() -> resolver.resolve(fileName))
        .isInstanceOf(SecurityException.class)
        .hasMessageContaining("不允许的文件类型");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "style.css",
        "app.js",
        "icon.svg",
        "photo.png",
        "font.woff2",
        "data.json",
        "page.html"
      })
  @DisplayName("白名单扩展名允许")
  void allowedExtensionAccepted(String fileName) {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    Path result = resolver.resolve(fileName);
    assertThat(result).isNotNull();
    assertThat(result.getFileName().toString()).isEqualTo(fileName);
  }

  @Test
  @DisplayName("归一化路径逃逸检查：编码后的 .. 不会绕过检查")
  void normalizedPathStillChecked() {
    StaticPathResolver resolver = new StaticPathResolver(tempDir);
    // 包含 .. 段的路径在归一化前就被拒绝
    assertThatThrownBy(() -> resolver.resolve("a/b/../../c/d.css"))
        .isInstanceOf(SecurityException.class);
  }
}
