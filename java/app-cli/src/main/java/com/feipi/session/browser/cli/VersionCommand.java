package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * version 子命令。
 *
 * <p>输出应用版本信息，等同 {@code --version} 选项。 版本内容来自 {@link BuildInfoVersionProvider}。
 */
@Command(name = "version", description = "输出版本信息")
final class VersionCommand implements Runnable {

  @Override
  public void run() {
    try {
      String[] version = new BuildInfoVersionProvider().getVersion();
      for (String line : version) {
        System.out.println(line);
      }
    } catch (Exception e) {
      System.err.println("版本信息读取失败: " + e.getMessage());
    }
  }
}
