package com.feipi.session.browser.cli;

import picocli.CommandLine;

/**
 * Session 会话浏览器的 CLI 应用入口。
 *
 * <p>负责引导 Picocli 命令行框架并委托给 {@code SessionBrowserCommand} 处理。
 */
public final class App {
  private App() {}

  /**
   * 应用程序主入口。
   *
   * @param args 命令行参数
   */
  public static void main(String[] args) {
    if (!"Mac OS X".equals(System.getProperty("os.name"))
        || !"aarch64".equals(System.getProperty("os.arch"))) {
      System.err.println("错误：仅支持 Apple Silicon macOS（arm64）。");
      System.exit(1);
    }
    final int exitCode = new CommandLine(new SessionBrowserCommand()).execute(args);
    System.exit(exitCode);
  }
}
