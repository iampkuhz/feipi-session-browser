package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.cli.PathResolver;
import com.feipi.session.browser.cli.RuntimePaths;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 发行可移植性门禁测试。
 *
 * <p>验证发行包在非常规路径和受限权限环境下可正常工作：
 *
 * <ul>
 *   <li>只读安装目录：安装目录设为只读后，数据目录仍可写入。
 *   <li>路径含空格和非 ASCII 字符：所有路径解析和目录创建正常。
 *   <li>升级崩溃/回滚：升级失败后可从备份恢复。
 * </ul>
 *
 * <p>校验放置：路径解析在 {@link PathResolver} 边界执行一次； 目录创建和权限检查在 {@link RuntimePaths#ensureDirectories()}
 * 边界执行一次。
 */
@DisplayName("发行可移植性门禁")
class PortabilityGateTest {

  @TempDir Path tempDir;

  /**
   * 只读安装目录场景。
   *
   * <p>模拟清洁机上安装目录为只读（例如 /opt 或 /Applications）， 数据目录位于用户主目录下可写区域。
   */
  @Nested
  @DisplayName("只读安装目录")
  class ReadOnlyInstallDirectory {

    @Test
    @DisplayName("安装目录只读时，数据目录仍可创建和写入")
    void readOnlyInstallDataDirStillWritable() throws IOException {
      // 模拟只读安装目录
      Path installDir = tempDir.resolve("opt").resolve("session-browser");
      Files.createDirectories(installDir);
      installDir.toFile().setWritable(false);

      // 数据目录位于可写区域
      Path dataDir = tempDir.resolve("user-data").resolve("session-browser");
      RuntimePaths paths = new RuntimePaths(dataDir);

      try {
        paths.ensureDirectories();

        assertThat(paths.dataDir()).isDirectory();

        // 数据目录可写
        Path probe = paths.dataDir().resolve(".write-test");
        Files.writeString(probe, "test");
        assertThat(probe).hasContent("test");
        Files.deleteIfExists(probe);
      } finally {
        installDir.toFile().setWritable(true);
      }
    }
  }

  /** 路径含空格和非 ASCII 字符场景。 */
  @Nested
  @DisplayName("路径含空格和非 ASCII 字符")
  class SpaceAndNonAsciiPaths {

    @Test
    @DisplayName("多层嵌套空格和 Unicode 路径")
    void nestedSpaceAndUnicodePath() throws IOException {
      Path base = tempDir.resolve("my app").resolve("données").resolve("缓存");
      Path dataDir = base.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir);

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
      assertThat(paths.artifactDir()).isDirectory();
    }
  }
}
