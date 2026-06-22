package com.feipi.session.browser.cli;

/**
 * Session 会话浏览器的 CLI 应用入口。
 *
 * <p>负责引导命令行界面并委托给 Picocli 命令处理器。
 */
public final class App {
  private App() {}

  /**
   * 应用程序主入口。
   *
   * @param args 命令行参数
   */
  public static void main(String[] args) {
    System.out.println("Feipi Session Browser");
  }
}
