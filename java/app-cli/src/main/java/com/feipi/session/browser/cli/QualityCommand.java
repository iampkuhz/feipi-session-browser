package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * quality 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 quality 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "quality", mixinStandardHelpOptions = true, description = "运行质量门禁检查")
final class QualityCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("quality 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh quality。");
  }
}
