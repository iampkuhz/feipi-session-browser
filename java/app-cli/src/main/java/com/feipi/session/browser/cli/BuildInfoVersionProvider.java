package com.feipi.session.browser.cli;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/**
 * 从 {@code build-info.properties} 读取版本信息。
 *
 * <p>版本信息由 Gradle 从 {@code java/gradle/VERSION} 生成，运行时不依赖源码树。
 */
final class BuildInfoVersionProvider {

  private static final String RESOURCE_PATH = "com/feipi/session/browser/cli/build-info.properties";

  /**
   * 读取当前应用版本号。
   *
   * <p>从构建时生成的 classpath 资源读取版本号，供升级流程写入 index_metadata。 运行时不依赖源码树。版本不可用时返回 null， 调用方应跳过版本追踪。
   *
   * @return 应用版本字符串，不可用时返回 null
   */
  static String readAppVersion() {
    Properties props = new Properties();
    try (InputStream in =
        BuildInfoVersionProvider.class.getClassLoader().getResourceAsStream(RESOURCE_PATH)) {
      if (in == null) {
        return null;
      }
      props.load(in);
    } catch (IOException e) {
      return null;
    }
    String version = props.getProperty("app.version");
    return (version != null && !version.isBlank()) ? version : null;
  }
}
