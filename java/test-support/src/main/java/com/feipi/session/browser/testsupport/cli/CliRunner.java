package com.feipi.session.browser.testsupport.cli;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

/**
 * CLI 进程级测试运行器。
 *
 * <p>通过 {@code ProcessBuilder} 启动 CLI 脚本，捕获 stdout、stderr 和退出码， 用于进程级契约测试。
 * 支持从任意工作目录运行，以及路径含空格的发行目录。
 */
public final class CliRunner {

  private final String scriptPath;
  private File workingDirectory;

  /**
   * 使用指定的 CLI 脚本路径创建运行器。
   *
   * @param scriptPath CLI 可执行脚本的绝对路径
   */
  public CliRunner(String scriptPath) {
    this.scriptPath = Objects.requireNonNull(scriptPath, "scriptPath 不得为空");
    this.workingDirectory = null;
  }

  /**
   * 设置子进程的工作目录。
   *
   * @param dir 工作目录；{@code null} 表示继承当前进程目录
   * @return 当前运行器实例，支持链式调用
   */
  public CliRunner workingDirectory(File dir) {
    this.workingDirectory = dir;
    return this;
  }

  /**
   * 使用给定参数运行 CLI 并捕获结果。
   *
   * @param args 传递给 CLI 脚本的参数
   * @return 包含 stdout、stderr 和退出码的 {@code CliResult}
   * @throws IOException 当进程启动或读取输出失败时抛出
   * @throws InterruptedException 当等待进程结束时被中断
   */
  public CliResult run(String... args) throws IOException, InterruptedException {
    String[] command = new String[args.length + 1];
    command[0] = scriptPath;
    System.arraycopy(args, 0, command, 1, args.length);

    ProcessBuilder pb = new ProcessBuilder(command);
    if (workingDirectory != null) {
      pb.directory(workingDirectory);
    }
    pb.redirectErrorStream(false);

    Process process = pb.start();

    String stdout;
    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
      stdout = readAll(reader);
    }

    String stderr;
    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
      stderr = readAll(reader);
    }

    int exitCode = process.waitFor();
    return new CliResult(stdout, stderr, exitCode);
  }

  private static String readAll(BufferedReader reader) throws IOException {
    StringBuilder sb = new StringBuilder();
    String line;
    while ((line = reader.readLine()) != null) {
      if (sb.length() > 0) {
        sb.append(System.lineSeparator());
      }
      sb.append(line);
    }
    return sb.toString();
  }

  /**
   * CLI 进程执行结果。
   *
   * @param stdout 标准输出内容（已去除末尾换行）
   * @param stderr 标准错误内容（已去除末尾换行）
   * @param exitCode 进程退出码
   */
  public record CliResult(String stdout, String stderr, int exitCode) {

    /**
     * 创建 CLI 执行结果。
     *
     * @param stdout 标准输出内容
     * @param stderr 标准错误内容
     * @param exitCode 退出码
     */
    public CliResult {
      stdout = stdout != null ? stdout : "";
      stderr = stderr != null ? stderr : "";
    }
  }
}
