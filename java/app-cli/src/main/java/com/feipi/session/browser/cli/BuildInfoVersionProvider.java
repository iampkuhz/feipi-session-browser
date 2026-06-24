package com.feipi.session.browser.cli;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import picocli.CommandLine.IVersionProvider;

/**
 * 从 {@code build-info.properties} 读取版本信息的 Picocli 版本提供者。
 *
 * <p>版本信息由 Gradle 在构建时从根 {@code VERSION} 文件生成， 运行时不依赖源码树。 当构建信息缺失或损坏时抛出异常， 因为发行包必须包含完整的构建信息。
 *
 * <p>此提供者不依赖 Picocli 注解框架，仅通过 classpath 资源 读取构建时生成的属性文件。
 */
final class BuildInfoVersionProvider implements IVersionProvider {

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

  /**
   * 获取版本信息字符串数组。
   *
   * @return 包含应用名称和版本号的单元素数组
   * @throws IOException 当构建信息文件缺失或 {@code app.version} 属性缺失时抛出
   */
  @Override
  public String[] getVersion() throws IOException {
    final Properties props = new Properties();
    try (InputStream in =
        BuildInfoVersionProvider.class.getClassLoader().getResourceAsStream(RESOURCE_PATH)) {
      if (in == null) {
        throw new IOException(
            "build-info.properties 缺失: 发行包应包含完整的构建信息，" + "请确认构建流程已正确生成 " + RESOURCE_PATH);
      }
      props.load(in);
    }
    final String version = props.getProperty("app.version");
    if (version == null || version.isBlank()) {
      throw new IOException("build-info.properties 中缺少 app.version 属性: " + "构建信息文件已损坏，请重新构建。");
    }
    final String name = props.getProperty("app.name", "feipi-session-browser");
    return new String[] {name + " " + version};
  }
}
