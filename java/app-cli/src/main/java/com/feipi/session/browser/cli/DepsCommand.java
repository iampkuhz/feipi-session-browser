package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * deps 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 deps 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "deps", mixinStandardHelpOptions = true, description = "安装或检查项目依赖")
final class DepsCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("deps 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh deps。");
  }
}
