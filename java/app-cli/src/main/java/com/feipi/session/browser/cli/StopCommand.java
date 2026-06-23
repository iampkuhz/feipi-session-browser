package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * stop 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 stop 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "stop", mixinStandardHelpOptions = true, description = "停止本地服务进程")
final class StopCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("stop 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh stop。");
  }
}
