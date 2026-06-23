package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * scan 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 scan 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "scan", mixinStandardHelpOptions = true, description = "扫描本地 agent 会话数据并建立索引")
final class ScanCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("scan 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh scan。");
  }
}
