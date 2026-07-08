package com.feipi.session.browser.contracttest.sourcespi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.SourceRoot;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceRoot} 契约测试。
 *
 * <p>验证源根安全检查：符号链接检测、路径逃逸判定和只读状态。 包含正向路径和负向路径（路径逃逸导致不安全）。
 */
@DisplayName("Source SPI — SourceRoot 安全契约")
class SourceRootContractTest {

  @Test
  @DisplayName("安全源根：无逃逸、无符号链接")
  void safeSourceRoot() {
    Path root = Path.of("/data/sessions");
    SourceRoot sr = new SourceRoot(root, root, false, false, false);
    assertThat(sr.isSafe()).isTrue();
    assertThat(sr.symlinkFollowed()).isFalse();
    assertThat(sr.pathEscapeDetected()).isFalse();
    assertThat(sr.readOnly()).isFalse();
  }

  @Test
  @DisplayName("路径逃逸导致不安全")
  void pathEscapeMakesUnsafe() {
    Path root = Path.of("/data/sessions");
    Path escaped = Path.of("/etc/passwd");
    SourceRoot sr = new SourceRoot(root, escaped, true, true, false);
    assertThat(sr.isSafe()).isFalse();
    assertThat(sr.symlinkFollowed()).isTrue();
    assertThat(sr.pathEscapeDetected()).isTrue();
  }

  @Test
  @DisplayName("符号链接但无逃逸仍安全")
  void symlinkWithoutEscapeIsSafe() {
    Path root = Path.of("/data/sessions");
    Path resolved = Path.of("/data/real-sessions");
    SourceRoot sr = new SourceRoot(root, resolved, true, false, false);
    assertThat(sr.isSafe()).isTrue();
    assertThat(sr.symlinkFollowed()).isTrue();
  }

  @Test
  @DisplayName("只读源根仍安全")
  void readOnlyIsSafe() {
    Path root = Path.of("/data/sessions");
    SourceRoot sr = new SourceRoot(root, root, false, false, true);
    assertThat(sr.isSafe()).isTrue();
    assertThat(sr.readOnly()).isTrue();
  }

  @Test
  @DisplayName("null rootPath 抛出 NullPointerException")
  void nullRootPathRejected() {
    assertThatThrownBy(() -> new SourceRoot(null, Path.of("/resolved"), false, false, false))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null resolvedPath 抛出 NullPointerException")
  void nullResolvedPathRejected() {
    assertThatThrownBy(() -> new SourceRoot(Path.of("/root"), null, false, false, false))
        .isInstanceOf(NullPointerException.class);
  }
}
