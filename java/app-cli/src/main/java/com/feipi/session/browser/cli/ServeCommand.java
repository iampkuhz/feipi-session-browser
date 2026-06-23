package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * serve 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 serve 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "serve", mixinStandardHelpOptions = true, description = "启动本地 Web 服务")
final class ServeCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("serve 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh serve。");
  }
}
