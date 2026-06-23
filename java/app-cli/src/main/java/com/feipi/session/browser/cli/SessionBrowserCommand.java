package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * Session 浏览器根命令。
 *
 * <p>提供 {@code --help} 和 {@code --version} 选项，并注册公开子命令。 已迁移到 Java 的子命令直接实现；未迁移的子命令以桩形式注册，
 * 运行时输出提示信息并引导用户使用 Shell 入口。 内部子命令（如 {@code normalized-batch}）通过 {@code hidden = true} 隐藏，不出现在 help
 * 输出中。
 */
@Command(
    name = "session-browser",
    mixinStandardHelpOptions = true,
    versionProvider = BuildInfoVersionProvider.class,
    subcommands = {
      ScanCommand.class,
      ServeCommand.class,
      StopCommand.class,
      TestCommand.class,
      DepsCommand.class,
      QualityCommand.class,
      VersionCommand.class,
      ReleaseCommand.class,
      NormalizedBatchCommand.class
    },
    description = "本地 agent 会话浏览器，索引和分析 Claude Code、Codex、Qoder 等会话数据。")
final class SessionBrowserCommand implements Runnable {

  @Override
  public void run() {
    System.out.println("使用 --help 查看可用命令。");
  }
}
