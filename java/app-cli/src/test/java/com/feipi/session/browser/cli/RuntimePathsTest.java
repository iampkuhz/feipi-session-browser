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
 * <p>验证跨平台路径解析、配置优先级、XDG Base Directory 兼容、目录创建和权限检查。 所有测试使用 {@link TempDir}
 * 隔离文件系统，不依赖真实用户主目录或环境变量。
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
      Path result = PathResolver.resolveDataDir(explicit.toString(), "INDEX_DIR");
      assertThat(result).isEqualTo(explicit);
    }

    @Test
    @DisplayName("空白显式路径回退到环境变量或默认值")
    void blankExplicitFallsThrough() {
      Path result = PathResolver.resolveDataDir("  ", "INDEX_DIR_NONEXISTENT_FOR_TEST");
      // 应回退到默认值（非 null，非空白）
      assertThat(result).isNotNull();
      assertThat(result.toString()).isNotEmpty();
    }

    @Test
    @DisplayName("null 显式路径回退到环境变量或默认值")
    void nullExplicitFallsThrough() {
      Path result = PathResolver.resolveDataDir(null, "INDEX_DIR_NONEXISTENT_FOR_TEST");
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
      Path result = PathResolver.resolveDataDir("~/test-data", "INDEX_DIR_NONEXISTENT_FOR_TEST");
      assertThat(result).isEqualTo(Path.of(home + "/test-data"));
    }
  }

  // ===== PathResolver 源数据目录 =====

  @Nested
  @DisplayName("PathResolver 源数据目录解析")
  class SourceDataDirContract {

    @Test
    @DisplayName("环境变量未设置时使用默认路径")
    void usesDefaultWhenEnvNotSet() {
      Path defaultPath = tempDir.resolve("default-source");
      Path result = PathResolver.resolveSourceDataDir("NONEXISTENT_ENV_VAR_FOR_TEST", defaultPath);
      assertThat(result).isEqualTo(defaultPath);
    }
  }

  // ===== PathResolver XDG 默认路径 =====

  @Nested
  @DisplayName("PathResolver 平台默认路径")
  class DefaultPathsContract {

    @Test
    @DisplayName("默认数据目录不为 null 且包含应用标识")
    void defaultDataDirNotNull() {
      Path dataDir = PathResolver.defaultDataDir();
      assertThat(dataDir).isNotNull();
      assertThat(dataDir.toString()).contains("feipi");
      assertThat(dataDir.toString()).contains("session-browser");
    }

    @Test
    @DisplayName("当前平台（macOS）默认数据目录使用 Library 结构")
    void macOSDefaultDataDir() {
      String os = System.getProperty("os.name", "").toLowerCase();
      if (!os.contains("mac")) {
        return; // 非 macOS 跳过
      }
      Path dataDir = PathResolver.defaultDataDir();
      assertThat(dataDir.toString()).contains("Library");
      assertThat(dataDir.toString()).contains("Application Support");
    }

    @Test
    @DisplayName("macOS 日志目录使用 Library/Logs 结构")
    void macOSLogDir() {
      String os = System.getProperty("os.name", "").toLowerCase();
      if (!os.contains("mac")) {
        return;
      }
      Path logDir = PathResolver.defaultLogDir(tempDir);
      assertThat(logDir.toString()).contains("Library");
      assertThat(logDir.toString()).contains("Logs");
    }

    @Test
    @DisplayName("macOS 缓存目录使用 Library/Caches 结构")
    void macOSCacheDir() {
      String os = System.getProperty("os.name", "").toLowerCase();
      if (!os.contains("mac")) {
        return;
      }
      Path cacheDir = PathResolver.defaultCacheDir(tempDir);
      assertThat(cacheDir.toString()).contains("Library");
      assertThat(cacheDir.toString()).contains("Caches");
    }

    @Test
    @DisplayName("日志目录和缓存目录不为 null")
    void logAndCacheDirNotNull() {
      assertThat(PathResolver.defaultLogDir(tempDir)).isNotNull();
      assertThat(PathResolver.defaultCacheDir(tempDir)).isNotNull();
    }
  }

  // ===== RuntimePaths 基础契约 =====

  @Nested
  @DisplayName("RuntimePaths 路径计算")
  class BasicContract {

    @Test
    @DisplayName("dbPath 位于数据目录下")
    void dbPathUnderDataDir() {
      RuntimePaths paths =
          new RuntimePaths(tempDir, tempDir.resolve("logs"), tempDir.resolve("cache"));
      assertThat(paths.dbPath()).isEqualTo(tempDir.resolve("index.sqlite"));
    }

    @Test
    @DisplayName("artifactDir 位于数据目录下")
    void artifactDirUnderDataDir() {
      RuntimePaths paths =
          new RuntimePaths(tempDir, tempDir.resolve("logs"), tempDir.resolve("cache"));
      assertThat(paths.artifactDir()).isEqualTo(tempDir.resolve("artifacts/normalized-sessions"));
    }

    @Test
    @DisplayName("pidFile 位于数据目录下")
    void pidFileUnderDataDir() {
      RuntimePaths paths =
          new RuntimePaths(tempDir, tempDir.resolve("logs"), tempDir.resolve("cache"));
      assertThat(paths.pidFile()).isEqualTo(tempDir.resolve("server.pid"));
    }

    @Test
    @DisplayName("fromDataDir 使用数据目录派生日志和缓存目录")
    void fromDataDirDerivesLogAndCache() {
      RuntimePaths paths = RuntimePaths.fromDataDir(tempDir);
      assertThat(paths.dataDir()).isEqualTo(tempDir);
      assertThat(paths.logDir()).isNotNull();
      assertThat(paths.cacheDir()).isNotNull();
    }

    @Test
    @DisplayName("dataDir 为 null 时抛出 NullPointerException")
    void nullDataDirRejected() {
      assertThatThrownBy(() -> new RuntimePaths(null, tempDir, tempDir))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("logDir 为 null 时抛出 NullPointerException")
    void nullLogDirRejected() {
      assertThatThrownBy(() -> new RuntimePaths(tempDir, null, tempDir))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("cacheDir 为 null 时抛出 NullPointerException")
    void nullCacheDirRejected() {
      assertThatThrownBy(() -> new RuntimePaths(tempDir, tempDir, null))
          .isInstanceOf(NullPointerException.class);
    }
  }

  // ===== RuntimePaths 目录创建 =====

  @Nested
  @DisplayName("RuntimePaths 目录创建与权限")
  class DirectoryCreationContract {

    @Test
    @DisplayName("ensureDirectories 创建数据、日志、缓存和制品目录")
    void ensureDirectoriesCreatesAll() throws IOException {
      Path dataDir = tempDir.resolve("data");
      Path logDir = tempDir.resolve("logs");
      Path cacheDir = tempDir.resolve("cache");
      RuntimePaths paths = new RuntimePaths(dataDir, logDir, cacheDir);

      paths.ensureDirectories();

      assertThat(dataDir).isDirectory();
      assertThat(logDir).isDirectory();
      assertThat(cacheDir).isDirectory();
      assertThat(paths.artifactDir()).isDirectory();
    }

    @Test
    @DisplayName("ensureDirectories 幂等：重复调用不抛异常")
    void ensureDirectoriesIdempotent() throws IOException {
      RuntimePaths paths =
          new RuntimePaths(
              tempDir.resolve("data"), tempDir.resolve("logs"), tempDir.resolve("cache"));

      paths.ensureDirectories();
      paths.ensureDirectories(); // 不抛异常即为通过
    }

    @Test
    @DisplayName("路径含空格时目录正常创建")
    void spacesInPath() throws IOException {
      Path base = tempDir.resolve("path with spaces");
      RuntimePaths paths =
          new RuntimePaths(base.resolve("data"), base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
      assertThat(paths.logDir()).isDirectory();
      assertThat(paths.cacheDir()).isDirectory();
    }

    @Test
    @DisplayName("路径含 Unicode 字符时目录正常创建")
    void unicodeInPath() throws IOException {
      Path base = tempDir.resolve("路径-テスト-데이터");
      RuntimePaths paths =
          new RuntimePaths(base.resolve("data"), base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
    }

    @Test
    @DisplayName("数据目录不可写时 ensureDirectories 抛出 IOException")
    void unwritableDataDirThrows() throws IOException {
      Path dataDir = tempDir.resolve("readonly-data");
      Files.createDirectories(dataDir);
      dataDir.toFile().setWritable(false);

      try {
        RuntimePaths paths =
            new RuntimePaths(dataDir, tempDir.resolve("logs"), tempDir.resolve("cache"));

        assertThatThrownBy(paths::ensureDirectories).isInstanceOf(IOException.class);
      } finally {
        // 恢复权限，确保 TempDir 清理可以执行
        dataDir.toFile().setWritable(true);
      }
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
      RuntimePaths paths = RuntimePaths.fromDataDir(absDataDir);
      paths.ensureDirectories();

      assertThat(paths.dbPath()).isAbsolute();
      assertThat(paths.artifactDir()).isAbsolute();
      assertThat(paths.pidFile()).isAbsolute();
    }
  }
}
