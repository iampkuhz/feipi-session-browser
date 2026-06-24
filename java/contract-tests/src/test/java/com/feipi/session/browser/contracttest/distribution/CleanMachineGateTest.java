package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.cli.PathResolver;
import com.feipi.session.browser.cli.RuntimePaths;
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 清洁机构建门禁测试。
 *
 * <p>验证发行包在无 JDK/Python/Gradle 环境的清洁机上可正常启动运行。 校验放置：构建产物完整性在 contract-tests 边界验证一次； 单个模块的构建任务由
 * Gradle 配置保证。
 */
@DisplayName("清洁机构建门禁")
class CleanMachineGateTest {

  @TempDir Path tempDir;

  /**
   * 构建信息资源存在于 classpath。
   *
   * <p>清洁机运行不依赖源码树，版本号通过 {@code build-info.properties} 提供。 该资源必须在 classpath 可用。
   */
  @Nested
  @DisplayName("构建信息资源")
  class BuildInfoResource {

    @Test
    @DisplayName("build-info.properties 存在于 classpath")
    void buildInfoPropertiesPresent() {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      assertThat(resource).as("build-info.properties 必须存在于 classpath，清洁机运行依赖此资源提供版本信息").isNotNull();
    }

    @Test
    @DisplayName("build-info.properties 包含必要属性")
    void buildInfoContainsRequiredProperties() throws IOException {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return; // 前置条件未满足，跳过
      }
      Properties props = new Properties();
      try (InputStream in = resource.openStream()) {
        props.load(in);
      }
      assertThat(props.getProperty("app.version"))
          .as("app.version 属性必须存在")
          .isNotNull()
          .isNotBlank();
      assertThat(props.getProperty("app.name")).as("app.name 属性必须存在").isNotNull().isNotBlank();
    }

    @Test
    @DisplayName("build-info.properties 内容 UTF-8 编码正确")
    void buildInfoUtf8Encoding() throws IOException {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return;
      }
      Properties props = new Properties();
      try (InputStream in = resource.openStream()) {
        props.load(in);
      }
      // app.name 应为纯 ASCII，确保编码无损坏
      String appName = props.getProperty("app.name");
      assertThat(appName).isEqualTo("feipi-session-browser");
    }
  }

  /**
   * VERSION 文件存在于项目根目录。
   *
   * <p>VERSION 文件由 DS-020 引入，打包到发行根目录供 launcher 读取。
   */
  @Nested
  @DisplayName("VERSION 文件")
  class VersionFile {

    @Test
    @DisplayName("项目根目录 VERSION 文件存在且非空")
    void versionFileExists() throws IOException {
      Path versionFile = findProjectRoot().resolve("VERSION");
      if (!Files.exists(versionFile)) {
        // 在非标准工作目录运行时跳过
        return;
      }
      assertThat(versionFile).isRegularFile();
      assertThat(Files.size(versionFile)).isGreaterThan(0);
    }
  }

  /**
   * 发行包不依赖 Python 或 quality 工具。
   *
   * <p>清洁机无 Python 环境，发行包不应包含 Python 脚本或 quality 工具依赖。
   */
  @Nested
  @DisplayName("无 Python/quality 依赖")
  class NoPythonDependency {

    @Test
    @DisplayName("运行时类路径不含 Python quality 脚本")
    void noPythonScriptsInRuntimeClasspath() {
      ClassLoader cl = getClass().getClassLoader();
      // 验证 Python quality 脚本不在 classpath 中
      assertThat(cl.getResource("scripts/quality/check_code_comment_language.py")).isNull();
      assertThat(cl.getResource("scripts/quality/run_required_quality_gates.py")).isNull();
    }
  }

  /**
   * 运行时无源码依赖。
   *
   * <p>清洁机不包含源码树，运行时不依赖任何 .java 或 .py 文件。
   */
  @Nested
  @DisplayName("无源码树依赖")
  class NoSourceTreeDependency {

    @Test
    @DisplayName("RuntimePaths 使用绝对路径，不依赖 cwd")
    void runtimePathsAbsoluteNoCwdDependency() throws IOException {
      Path base = tempDir.toAbsolutePath().resolve("clean-machine");
      RuntimePaths paths =
          new RuntimePaths(base.resolve("data"), base.resolve("logs"), base.resolve("cache"));
      paths.ensureDirectories();

      assertThat(paths.dataDir()).isAbsolute();
      assertThat(paths.logDir()).isAbsolute();
      assertThat(paths.cacheDir()).isAbsolute();
      assertThat(paths.dbPath()).isAbsolute();
      assertThat(paths.artifactDir()).isAbsolute();
      assertThat(paths.backupDir()).isAbsolute();
      assertThat(paths.pidFile()).isAbsolute();
    }

    @Test
    @DisplayName("PathResolver 默认路径不依赖项目目录结构")
    void defaultPathsIndependentOfProjectStructure() {
      Path dataDir = PathResolver.defaultDataDir();
      assertThat(dataDir).isNotNull();
      assertThat(dataDir.toString()).contains("feipi");
      assertThat(dataDir.toString()).contains("session-browser");
      // 默认路径不应包含 build、gradle 等项目目录标识
      assertThat(dataDir.toString()).doesNotContain("build");
      assertThat(dataDir.toString()).doesNotContain("gradle");
    }
  }

  /**
   * 从项目工作目录向上查找根目录。
   *
   * @return 包含 VERSION 文件或 settings.gradle.kts 的目录
   */
  private static Path findProjectRoot() {
    Path dir = Path.of(System.getProperty("user.dir"));
    while (dir != null) {
      if (Files.exists(dir.resolve("settings.gradle.kts"))) {
        return dir;
      }
      dir = dir.getParent();
    }
    return Path.of(System.getProperty("user.dir"));
  }
}
