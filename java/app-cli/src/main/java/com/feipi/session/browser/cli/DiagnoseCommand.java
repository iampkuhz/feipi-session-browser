package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;

/**
 * diagnose 父命令。
 *
 * <p>提供 session 子命令用于诊断 session 数据管道各层状态。
 */
@Command(
    name = "diagnose",
    description = "诊断 session 数据管道",
    subcommands = {DiagnoseSessionCommand.class},
    mixinStandardHelpOptions = true)
final class DiagnoseCommand implements Runnable {

  @Override
  public void run() {
    System.out.println("使用 diagnose --help 查看可用子命令。");
  }
}
