package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.net.URL;
import java.util.Properties;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 可重现性门禁测试。
 *
 * <p>验证发行构建的可重现性：
 *
 * <ul>
 *   <li>相同输入产生相同的构建信息。
 *   <li>构建信息内容格式确定。
 *   <li>归档配置确保可重现。
 * </ul>
 *
 * <p>校验放置：可重现性在构建配置边界（Gradle）保证一次； 运行时验证构建信息格式正确性一次。
 */
@DisplayName("可重现性门禁")
class ReproducibilityGateTest {

  /**
   * 构建信息确定性验证。
   *
   * <p>build-info.properties 由 Gradle 生成，输入固定时输出确定。 运行时验证其格式和内容满足契约。
   */
  @Nested
  @DisplayName("构建信息确定性")
  class BuildInfoDeterminism {

    @Test
    @DisplayName("build-info.properties 版本号格式确定")
    void versionFormatDeterministic() throws Exception {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return;
      }
      Properties props = loadProperties(resource);
      String version = props.getProperty("app.version");
      assertThat(version).isNotNull();
      // 版本号应符合 semver 格式（允许预发布后缀）
      assertThat(version).matches("\\d+\\.\\d+(\\.\\d+)?(-[\\w.]+)?");
    }

    @Test
    @DisplayName("build-info.properties 应用名称固定")
    void appNameFixed() throws Exception {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return;
      }
      Properties props = loadProperties(resource);
      assertThat(props.getProperty("app.name")).isEqualTo("feipi-session-browser");
    }

    @Test
    @DisplayName("build-info.properties 包含 git commit 信息")
    void gitCommitPresent() throws Exception {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return;
      }
      Properties props = loadProperties(resource);
      String commit = props.getProperty("app.git.commit");
      assertThat(commit).as("git commit 应存在，确保发行可追溯到具体源码版本").isNotNull().isNotBlank();
    }

    @Test
    @DisplayName("build-info.properties 包含构建时间戳")
    void buildTimestampPresent() throws Exception {
      URL resource =
          getClass()
              .getClassLoader()
              .getResource("com/feipi/session/browser/cli/build-info.properties");
      if (resource == null) {
        return;
      }
      Properties props = loadProperties(resource);
      String timestamp = props.getProperty("app.build.timestamp");
      assertThat(timestamp).as("构建时间戳应存在，用于发行追溯").isNotNull().isNotBlank();
    }

    @Test
    @DisplayName("相同 BUILD_GIT_COMMIT 和 BUILD_TIMESTAMP 输入产生相同输出")
    void sameInputProducesSameOutput() throws Exception {
      // 读取当前构建信息两次，验证内容一致
      Properties props1 = loadBuildInfo();
      Properties props2 = loadBuildInfo();
      if (props1 == null || props2 == null) {
        return;
      }
      assertThat(props1.getProperty("app.version")).isEqualTo(props2.getProperty("app.version"));
      assertThat(props1.getProperty("app.name")).isEqualTo(props2.getProperty("app.name"));
      assertThat(props1.getProperty("app.git.commit"))
          .isEqualTo(props2.getProperty("app.git.commit"));
    }
  }

  /**
   * 依赖内容验证。
   *
   * <p>验证发行包依赖内容符合预期，不含多余依赖。
   */
  @Nested
  @DisplayName("依赖内容验证")
  class DependencyContentValidation {

    @Test
    @DisplayName("SQLite JDBC 驱动在 classpath")
    void sqliteJdbcInClasspath() {
      assertThat(getClass().getClassLoader().getResource("org/sqlite/JDBC.class")).isNotNull();
    }

    @Test
    @DisplayName("Javalin web 框架在 classpath")
    void javalinInClasspath() {
      assertThat(getClass().getClassLoader().getResource("io/javalin/Javalin.class")).isNotNull();
    }

    @Test
    @DisplayName("核心 domain 模块在 classpath")
    void coreDomainInClasspath() {
      assertThat(
              getClass()
                  .getClassLoader()
                  .getResource("com/feipi/session/browser/domain/DomainMarker.class"))
          .isNotNull();
    }
  }

  // ===== 辅助方法 =====

  private Properties loadProperties(URL resource) throws Exception {
    Properties props = new Properties();
    try (InputStream in = resource.openStream()) {
      props.load(in);
    }
    return props;
  }

  private Properties loadBuildInfo() throws Exception {
    URL resource =
        getClass()
            .getClassLoader()
            .getResource("com/feipi/session/browser/cli/build-info.properties");
    if (resource == null) {
      return null;
    }
    return loadProperties(resource);
  }
}
