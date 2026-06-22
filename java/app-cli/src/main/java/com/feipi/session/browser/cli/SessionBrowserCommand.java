package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * Session 浏览器根命令。
 *
 * <p>提供 {@code --help} 和 {@code --version} 选项。 未来内部子命令在此注册但不对外暴露。
 */
@Command(
    name = "session-browser",
    mixinStandardHelpOptions = true,
    versionProvider = BuildInfoVersionProvider.class,
    description = "本地 agent 会话浏览器，索引和分析 Claude Code、Codex、Qoder 等会话数据。")
final class SessionBrowserCommand implements Runnable {

  @Override
  public void run() {
    System.out.println("使用 --help 查看可用命令。");
  }
}
