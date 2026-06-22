package com.feipi.session.browser.cli;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import picocli.CommandLine.IVersionProvider;

/**
 * 从 {@code build-info.properties} 读取版本号的 Picocli 版本提供者。
 *
 * <p>版本信息由 Gradle 在构建时从根 {@code VERSION} 文件生成， 运行时不依赖源码树。
 */
final class BuildInfoVersionProvider implements IVersionProvider {

  private static final String RESOURCE_PATH = "com/feipi/session/browser/cli/build-info.properties";

  @Override
  public String[] getVersion() throws IOException {
    final Properties props = new Properties();
    try (InputStream in =
        BuildInfoVersionProvider.class.getClassLoader().getResourceAsStream(RESOURCE_PATH)) {
      if (in == null) {
        return new String[] {"feipi-session-browser (version unavailable)"};
      }
      props.load(in);
    }
    final String version = props.getProperty("app.version", "unknown");
    return new String[] {"feipi-session-browser " + version};
  }
}
