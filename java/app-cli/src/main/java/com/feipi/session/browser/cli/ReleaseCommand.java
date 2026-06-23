package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * release 子命令桩实现。
 *
 * <p>当前 Java 尚未实现 release/build 功能，运行时输出提示信息并以非零退出码退出。
 */
@Command(name = "release", mixinStandardHelpOptions = true, description = "构建发行包")
final class ReleaseCommand implements Runnable {

  @Override
  public void run() {
    System.err.println("release 命令尚未在 Java 版本中实现，请使用 ./scripts/session-browser.sh release-check。");
  }
}
