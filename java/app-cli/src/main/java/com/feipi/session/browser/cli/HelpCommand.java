package com.feipi.session.browser.cli;

import picocli.CommandLine.Command;
import picocli.CommandLine.Model.CommandSpec;
import picocli.CommandLine.Spec;

/**
 * help 子命令。
 *
 * <p>输出根命令的公开帮助信息，作为 {@code --help} 的子命令别名。
 */
@Command(name = "help", description = "显示帮助信息")
final class HelpCommand implements Runnable {

  @Spec private CommandSpec spec;

  @Override
  public void run() {
    spec.parent().commandLine().usage(System.out);
  }
}
