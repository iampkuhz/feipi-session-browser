package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * RuntimePaths 与 PathResolver 契约测试。
 *
 * <p>验证macOS 版本化路径、配置优先级、目录创建和权限检查。 所有测试使用 {@link TempDir} 隔离文件系统，不依赖真实用户主目录或环境变量。
 */
@DisplayName("RuntimePaths 与 PathResolver 契约测试")
class RuntimePathsTest {

  @TempDir Path tempDir;

  // ===== PathResolver 配置优先级 =====

  @Nested
  @DisplayName("PathResolver 配置优先级：CLI > env > default")
  class PrecedenceContract {

    @Test
    @DisplayName("显式路径优先于环境变量和默认值")
    void explicitPathTakesPrecedence() {
      Path explicit = tempDir.resolve("explicit-data");
      Path result = PathResolver.resolveDataDir(explicit.toString());
      assertThat(result).isEqualTo(explicit);
    }

    @Test
    @DisplayName("空白显式路径回退到环境变量或默认值")
    void blankExplicitFallsThrough() {
      Path result = PathResolver.resolveDataDir("  ");
      // 应回退到默认值（非 null，非空白）
      assertThat(result).isNotNull();
      assertThat(result.toString()).isNotEmpty();
    }

    @Test
    @DisplayName("null 显式路径回退到环境变量或默认值")
    void nullExplicitFallsThrough() {
      Path result = PathResolver.resolveDataDir(null);
      assertThat(result).isNotNull();
    }
  }

  // ===== PathResolver 路径展开 =====

  @Nested
  @DisplayName("PathResolver 路径展开")
  class TildeExpansionContract {

    @Test
    @DisplayName("显式路径中 ~ 被展开为用户主目录")
    void tildeExpandedInExplicitPath() {
      String home = System.getProperty("user.home");
      Path result = PathResolver.resolveDataDir("~/test-data");
      assertThat(result).isEqualTo(Path.of(home + "/test-data"));
    }
  }

  // ===== PathResolver 版本化默认路径 =====

  @Nested
  @DisplayName("PathResolver 平台默认路径")
  class DefaultPathsContract {

    @Test
    @DisplayName("默认数据目录不为 null 且包含应用标识")
    void defaultDataDirNotNull() {
      Path dataDir = PathResolver.defaultDataDir();
      assertThat(dataDir).isNotNull();
      assertThat(dataDir.toString()).contains("feipi");
      assertThat(dataDir.getParent().getFileName().toString()).isEqualTo("session-browser");
      assertThat(dataDir.getFileName().toString())
          .isEqualTo(BuildInfoVersionProvider.readAppVersion());
    }

    @Test
    @DisplayName("当前平台（macOS）默认数据目录使用 Library 结构")
    void macOSDefaultDataDir() {
      Path dataDir = PathResolver.defaultDataDir();
      assertThat(dataDir.toString()).contains("Library");
      assertThat(dataDir.toString()).contains("Application Support");
    }
  }

  // ===== RuntimePaths 基础契约 =====

  @Nested
  @DisplayName("RuntimePaths 路径计算")
  class BasicContract {

    @Test
    @DisplayName("dbPath 位于数据目录下")
    void dbPathUnderDataDir() {
      RuntimePaths paths = new RuntimePaths(tempDir);
      assertThat(paths.dbPath()).isEqualTo(tempDir.resolve(RuntimePaths.DB_FILE_NAME));
    }

    @Test
    @DisplayName("artifactDir 位于数据目录下")
    void artifactDirUnderDataDir() {
      RuntimePaths paths = new RuntimePaths(tempDir);
      assertThat(paths.artifactDir()).isEqualTo(tempDir.resolve("artifacts/normalized-sessions"));
    }

    @Test
    @DisplayName("pidFile 位于数据目录下")
    void pidFileUnderDataDir() {
      RuntimePaths paths = new RuntimePaths(tempDir);
      assertThat(paths.pidFile()).isEqualTo(tempDir.resolve("server.pid"));
    }

    @Test
    @DisplayName("dataDir 为 null 时抛出 NullPointerException")
    void nullDataDirRejected() {
      assertThatThrownBy(() -> new RuntimePaths(null)).isInstanceOf(NullPointerException.class);
    }
  }

  // ===== RuntimePaths 目录创建 =====

  @Nested
  @DisplayName("RuntimePaths 目录创建与权限")
  class DirectoryCreationContract {

    @Test
    @DisplayName("ensureDirectories 创建数据和制品目录")
    void ensureDirectoriesCreatesAll() throws IOException {
      Path dataDir = tempDir.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir);

      paths.ensureDirectories();

      assertThat(dataDir).isDirectory();
      assertThat(paths.artifactDir()).isDirectory();
    }

    @Test
    @DisplayName("ensureDirectories 幂等：重复调用不抛异常")
    void ensureDirectoriesIdempotent() throws IOException {
      RuntimePaths paths = new RuntimePaths(tempDir.resolve("data"));

      paths.ensureDirectories();
      paths.ensureDirectories(); // 不抛异常即为通过
    }

    @Test
    @DisplayName("路径含空格时目录正常创建")
    void spacesInPath() throws IOException {
      Path base = tempDir.resolve("path with spaces");
      RuntimePaths paths = new RuntimePaths(base.resolve("data"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
    }

    @Test
    @DisplayName("路径含 Unicode 字符时目录正常创建")
    void unicodeInPath() throws IOException {
      Path base = tempDir.resolve("路径-テスト-데이터");
      RuntimePaths paths = new RuntimePaths(base.resolve("data"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
    }

    @Test
    @DisplayName("数据目录被普通文件阻断时 ensureDirectories 抛出 IOException")
    void unavailableDataDirThrows() throws IOException {
      // 普通文件不能作为父目录；不依赖 文件权限或执行用户身份。
      Path blocker = Files.createFile(tempDir.resolve("data-parent-file"));
      Path dataDir = blocker.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir);

      assertThat(blocker).isRegularFile();
      assertThatThrownBy(paths::ensureDirectories).isInstanceOf(IOException.class);
    }
  }

  // ===== 无 cwd 依赖验证 =====

  @Nested
  @DisplayName("无 cwd 依赖")
  class NoCwdDependencyContract {

    @Test
    @DisplayName("RuntimePaths 使用绝对路径时不依赖 cwd")
    void absolutePathNoCwdDependency() throws IOException {
      Path absDataDir = tempDir.toAbsolutePath().resolve("abs-data");
      RuntimePaths paths = new RuntimePaths(absDataDir);
      paths.ensureDirectories();

      assertThat(paths.dbPath()).isAbsolute();
      assertThat(paths.artifactDir()).isAbsolute();
      assertThat(paths.pidFile()).isAbsolute();
    }
  }
}
