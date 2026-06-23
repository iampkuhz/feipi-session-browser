package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * test 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 test 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "test", mixinStandardHelpOptions = true, description = "运行测试套件")
final class TestCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("test 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh test。");
  }
}
