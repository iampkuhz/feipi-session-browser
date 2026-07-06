package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * version 子命令。
 *
 * <p>输出应用版本号，等同 {@code --version} 选项。版本内容来自 {@link BuildInfoVersionProvider#readAppVersion()}。
 */
@Command(name = "version", description = "输出版本信息")
final class VersionCommand implements Runnable {

  @Override
  public void run() {
    String version = BuildInfoVersionProvider.readAppVersion();
    if (version == null) {
      System.err.println("版本信息读取失败: build-info.properties 缺失或 app.version 为空");
      return;
    }
    System.out.println(version);
  }

  static void printVersion() {
    new VersionCommand().run();
  }
}
