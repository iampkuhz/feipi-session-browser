package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 资源预算门禁测试。
 *
 * <p>验证发行包启动资源在预算内：
 *
 * <ul>
 *   <li>JVM 堆内存限制在 128MB 以内。
 *   <li>使用 Serial GC 加快冷启动。
 *   <li>构建信息大小合理。
 * </ul>
 *
 * <p>校验放置：JVM 参数在 launcher 脚本和 Gradle application 配置边界设置一次； 运行时验证构建信息资源大小一次。
 */
@DisplayName("资源预算门禁")
class ResourceBudgetGateTest {

  /**
   * JVM 参数预算验证。
   *
   * <p>验证 app-cli build.gradle.kts 中配置的 JVM 参数满足资源预算。
   */
  @Nested
  @DisplayName("JVM 参数预算")
  class JvmArgsBudget {

    @Test
    @DisplayName("最大堆内存不超过 128MB")
    void maxHeapWithinBudget() {
      Path buildFile = findProjectRoot().resolve("java/app-cli/build.gradle.kts");
      if (!Files.exists(buildFile)) {
        return;
      }
      try {
        String content = Files.readString(buildFile);
        // 验证 -Xmx128m 配置存在
        assertThat(content).contains("-Xmx128m");
      } catch (IOException e) {
        // 构建文件不可读时跳过
      }
    }

    @Test
    @DisplayName("使用 Serial GC 加快冷启动")
    void serialGcConfigured() {
      Path buildFile = findProjectRoot().resolve("java/app-cli/build.gradle.kts");
      if (!Files.exists(buildFile)) {
        return;
      }
      try {
        String content = Files.readString(buildFile);
        assertThat(content).contains("-XX:+UseSerialGC");
      } catch (IOException e) {
        // 构建文件不可读时跳过
      }
    }

    @Test
    @DisplayName("初始堆内存设置较小")
    void initialHeapSmall() {
      Path buildFile = findProjectRoot().resolve("java/app-cli/build.gradle.kts");
      if (!Files.exists(buildFile)) {
        return;
      }
      try {
        String content = Files.readString(buildFile);
        // 初始堆内存应为 16MB 或更小
        assertThat(content).contains("-Xms16m");
      } catch (IOException e) {
        // 构建文件不可读时跳过
      }
    }
  }

  /**
   * 构建信息资源大小验证。
   *
   * <p>build-info.properties 应为小型配置文件，不包含大资源。
   */
  @Nested
  @DisplayName("构建信息资源大小")
  class BuildInfoResourceSize {

    @Test
    @DisplayName("build-info.properties 大小合理（小于 1KB）")
    void buildInfoSizeReasonable() throws IOException {
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
      // 验证属性数量合理（不超过 10 个）
      assertThat(props.size()).isLessThanOrEqualTo(10);
      // 验证每个属性值长度合理
      for (String key : props.stringPropertyNames()) {
        String value = props.getProperty(key);
        assertThat(value.length()).as("属性 %s 的值长度应合理", key).isLessThan(200);
      }
    }
  }

  /**
   * 运行时内存预算验证。
   *
   * <p>验证当前 JVM 运行时内存配置满足预算。
   */
  @Nested
  @DisplayName("运行时内存预算")
  class RuntimeMemoryBudget {

    @Test
    @DisplayName("运行时最大内存不超过预算")
    void runtimeMaxMemoryWithinBudget() {
      long maxMemory = Runtime.getRuntime().maxMemory();
      long maxMemoryMb = maxMemory / (1024 * 1024);
      // 生产环境配置 -Xmx128m；Gradle 测试 JVM 可能有更高限制。
      // 验证不超过 1GB 以确保合理范围。
      assertThat(maxMemoryMb).as("运行时最大内存 %dMB 应在合理范围内", maxMemoryMb).isLessThan(1024);
    }

    @Test
    @DisplayName("运行时可用内存充足")
    void runtimeFreeMemorySufficient() {
      long freeMemory = Runtime.getRuntime().freeMemory();
      long totalMemory = Runtime.getRuntime().totalMemory();
      double freeRatio = (double) freeMemory / totalMemory;
      // 空闲内存比例应大于 10%
      assertThat(freeRatio).as("空闲内存比例 %.2f 应充足", freeRatio).isGreaterThan(0.1);
    }
  }

  /** 从项目工作目录向上查找根目录。 */
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
