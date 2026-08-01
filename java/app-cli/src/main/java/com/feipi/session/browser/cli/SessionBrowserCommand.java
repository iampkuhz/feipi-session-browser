package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * Session 浏览器根命令。
 *
 * <p>提供 {@code --help} 和 {@code --version} 选项，并仅注册具有真实 Java 实现的公开子命令。内部子命令（如 {@code
 * normalized-batch}）通过 {@code hidden = true} 隐藏，不出现在 help 输出中。
 */
@Command(
    name = "session-browser",
    mixinStandardHelpOptions = false,
    subcommands = {
      HelpCommand.class,
      ScanCommand.class,
      ServeCommand.class,
      StopCommand.class,
      StatusCommand.class,
      DoctorCommand.class,
      DepsCommand.class,
      VersionCommand.class,
      NormalizedBatchCommand.class,
      DiagnoseCommand.class
    },
    description = "本地 agent 会话浏览器，索引和分析 Claude Code、Codex、Qoder 等会话数据。")
final class SessionBrowserCommand implements Runnable {

  @Option(
      names = {"-h", "--help"},
      usageHelp = true,
      description = "显示帮助信息并退出。")
  private boolean helpRequested;

  @Option(
      names = {"-V", "--version"},
      description = "输出版本信息并退出。")
  private boolean versionRequested;

  @Override
  public void run() {
    if (printVersionIfRequested()) {
      return;
    }
    printUsageHint();
  }

  private boolean printVersionIfRequested() {
    if (!versionRequested) {
      return false;
    }
    VersionCommand.printVersion();
    return true;
  }

  private static void printUsageHint() {
    System.out.println("使用 --help 查看可用命令。");
  }
}
