package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;

/**
 * CLI help/version 契约测试。
 *
 * <p>验证 no-arg、help、version、未知参数和多余参数的 stdout/stderr/exit code 行为矩阵， 以及发行目录的可重定位运行。
 */
@DisplayName("CLI help/version 契约测试")
class CliContractTest {

  /**
   * 运行 CLI 命令并捕获输出结果。
   *
   * @param args 命令行参数
   * @return 包含 stdout、stderr 和退出码的结果记录
   */
  private static CliExecution execute(String... args) {
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    ByteArrayOutputStream stderrBytes = new ByteArrayOutputStream();
    PrintStream origOut = System.out;
    PrintStream origErr = System.err;
    int exitCode;
    try {
      System.setOut(new PrintStream(stdoutBytes));
      System.setErr(new PrintStream(stderrBytes));
      exitCode = new CommandLine(new SessionBrowserCommand()).execute(args);
    } finally {
      System.setOut(origOut);
      System.setErr(origErr);
    }
    return new CliExecution(stdoutBytes.toString().trim(), stderrBytes.toString().trim(), exitCode);
  }

  /** 单次 CLI 执行的输出捕获结果。 */
  private record CliExecution(String stdout, String stderr, int exitCode) {}

  // ===== 进程级契约测试（依赖 installDist 产物） =====

  /** installDist 产物路径，通过系统属性或默认路径定位。 */
  private static Path installDir;

  /**
   * 初始化 installDist 产物路径。
   *
   * <p>优先使用 {@code cli.install.dir} 系统属性，否则使用项目默认构建路径。 当产物不存在时跳过进程级测试。
   */
  @BeforeAll
  static void resolveInstallDir() {
    String dirProp = System.getProperty("cli.install.dir");
    if (dirProp != null) {
      installDir = Path.of(dirProp);
    } else {
      // 默认 Gradle installDist 输出路径
      installDir = Path.of("build/install/app-cli");
    }
  }

  /**
   * 获取 CLI 脚本路径。
   *
   * @return CLI 启动脚本的绝对路径
   */
  private Path cliScript() {
    return installDir.resolve("bin").resolve("app-cli");
  }

  // ===== help 契约 =====

  @Nested
  @DisplayName("--help / -h 输出契约")
  class HelpContract {

    @Test
    @DisplayName("--help 输出到 stdout，exit code = 0")
    void longHelpFlag() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
      assertThat(result.stdout()).contains("--help");
      assertThat(result.stdout()).contains("--version");
    }

    @Test
    @DisplayName("-h 输出到 stdout，exit code = 0")
    void shortHelpFlag() {
      CliExecution result = execute("-h");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
    }

    @Test
    @DisplayName("help 隐藏内部命令（normalized-batch），展示公开子命令")
    void helpHidesInternalCommands() {
      CliExecution result = execute("--help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stdout()).doesNotContain("normalized-batch");
      assertThat(result.stdout())
          .contains("help")
          .contains("scan")
          .contains("serve")
          .contains("stop")
          .contains("status")
          .contains("doctor")
          .contains("test")
          .contains("deps")
          .contains("quality")
          .contains("version")
          .contains("release");
    }

    @Test
    @DisplayName("help 子命令输出公开 help，exit code = 0")
    void helpSubcommandShowsPublicHelp() {
      CliExecution result = execute("help");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("session-browser");
      assertThat(result.stdout()).contains("--help");
      assertThat(result.stdout()).contains("--version");
      assertThat(result.stdout()).contains("scan").contains("serve").contains("stop");
      assertThat(result.stdout()).doesNotContain("normalized-batch");
    }
  }

  // ===== version 契约 =====

  @Nested
  @DisplayName("--version / -V 输出契约")
  class VersionContract {

    @Test
    @DisplayName("--version 输出到 stdout，exit code = 0")
    void longVersionFlag() {
      CliExecution result = execute("--version");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).startsWith("feipi-session-browser");
      // 版本号应为非空字符串
      assertThat(result.stdout()).matches("feipi-session-browser \\S+");
    }

    @Test
    @DisplayName("-V 输出到 stdout，exit code = 0")
    void shortVersionFlag() {
      CliExecution result = execute("-V");

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).startsWith("feipi-session-browser");
    }

    @Test
    @DisplayName("BuildInfoVersionProvider 读取 classpath 中的 build-info.properties")
    void versionFromBuildInfo() throws Exception {
      BuildInfoVersionProvider provider = new BuildInfoVersionProvider();
      String[] version = provider.getVersion();

      assertThat(version).hasSize(1);
      assertThat(version[0]).startsWith("feipi-session-browser");
      assertThat(version[0]).containsPattern("\\d+");
    }

    @Test
    @DisplayName("--version 后跟多余参数输出错误到 stderr，exit code = 2")
    void versionFlagRejectsExtraArgs() {
      CliExecution result = execute("--version", "extra");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stdout()).isEmpty();
      assertThat(result.stderr()).contains("Unmatched argument");
      assertThat(result.stderr()).contains("extra");
    }
  }

  // ===== no-arg 契约 =====

  @Nested
  @DisplayName("无参数执行契约")
  class NoArgContract {

    @Test
    @DisplayName("无参数时输出提示信息到 stdout，exit code = 0")
    void noArgsShowsUsageHint() {
      CliExecution result = execute();

      assertThat(result.exitCode()).isEqualTo(0);
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("--help");
    }
  }

  // ===== 未知参数契约 =====

  @Nested
  @DisplayName("未知参数契约")
  class UnknownArgsContract {

    @Test
    @DisplayName("未知长选项输出错误到 stderr，exit code = 2")
    void unknownLongOption() {
      CliExecution result = execute("--unknown");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
      assertThat(result.stderr()).contains("--unknown");
    }

    @Test
    @DisplayName("未知短选项输出错误到 stderr，exit code = 2")
    void unknownShortOption() {
      CliExecution result = execute("-z");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }

  // ===== 多余参数契约 =====

  @Nested
  @DisplayName("多余参数契约")
  class ExtraArgsContract {

    @Test
    @DisplayName("多余位置参数输出错误到 stderr，exit code = 2")
    void extraPositionalArgs() {
      CliExecution result = execute("extra1", "extra2");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unmatched arguments");
    }

    @Test
    @DisplayName("合法选项后跟多余参数输出错误到 stderr，exit code = 2")
    void validOptionThenExtraArgs() {
      // 位置参数 "subcommand" 不被接受，Picocli 报参数不匹配错误
      CliExecution result = execute("subcommand");

      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unmatched argument");
    }
  }

  // ===== 进程级发行目录测试 =====

  @Nested
  @DisplayName("发行目录进程级契约")
  class DistributionContract {

    @Test
    @DisplayName("从任意 cwd 运行 installDist 产物 --help")
    void distHelpFromArbitraryCwd() throws Exception {
      Path script = cliScript();
      if (!Files.exists(script)) {
        // installDist 未运行时跳过
        return;
      }
      script.toFile().setExecutable(true);

      ProcessBuilder pb = new ProcessBuilder(script.toAbsolutePath().toString(), "--help");
      pb.directory(Files.createTempDirectory("cli-test-cwd").toFile());
      pb.redirectErrorStream(false);
      Process process = pb.start();
      String stdout = new String(process.getInputStream().readAllBytes());
      process.getErrorStream().readAllBytes();
      int exitCode = process.waitFor();

      assertThat(exitCode).isZero();
      assertThat(stdout).contains("session-browser");
    }

    @Test
    @DisplayName("从路径含空格的发行目录运行 --version")
    void distVersionFromPathWithSpaces() throws Exception {
      Path script = cliScript();
      if (!Files.exists(script)) {
        return;
      }

      // 复制到路径含空格的临时目录
      Path spaceDir = Files.createTempDirectory("cli test path with spaces");
      Path spaceBin = spaceDir.resolve("bin");
      Path spaceLib = spaceDir.resolve("lib");
      Files.createDirectories(spaceBin);
      Files.createDirectories(spaceLib);

      Path origBin = installDir.resolve("bin");
      Path origLib = installDir.resolve("lib");
      if (Files.exists(origBin)) {
        try (var stream = Files.walk(origBin)) {
          stream.forEach(
              source -> {
                try {
                  Path target = spaceBin.resolve(origBin.relativize(source));
                  if (Files.isDirectory(source)) {
                    Files.createDirectories(target);
                  } else {
                    Files.copy(source, target);
                  }
                } catch (Exception e) {
                  throw new RuntimeException(e);
                }
              });
        }
      }
      if (Files.exists(origLib)) {
        try (var stream = Files.walk(origLib)) {
          stream.forEach(
              source -> {
                try {
                  Path target = spaceLib.resolve(origLib.relativize(source));
                  if (Files.isDirectory(source)) {
                    Files.createDirectories(target);
                  } else {
                    Files.copy(source, target);
                  }
                } catch (Exception e) {
                  throw new RuntimeException(e);
                }
              });
        }
      }

      Path relocatedScript = spaceBin.resolve("app-cli");
      relocatedScript.toFile().setExecutable(true);

      ProcessBuilder pb =
          new ProcessBuilder(relocatedScript.toAbsolutePath().toString(), "--version");
      pb.directory(Files.createTempDirectory("cli-test-cwd").toFile());
      pb.redirectErrorStream(false);
      Process process = pb.start();
      String stdout = new String(process.getInputStream().readAllBytes());
      String stderr = new String(process.getErrorStream().readAllBytes());
      int exitCode = process.waitFor();

      assertThat(exitCode).withFailMessage("发行目录路径含空格运行失败: stderr=%s", stderr).isZero();
      assertThat(stdout).contains("feipi-session-browser");

      // 清理测试创建的临时目录
      deleteRecursively(spaceDir);
    }
  }

  private static void deleteRecursively(Path path) {
    try {
      if (Files.isDirectory(path)) {
        try (var entries = Files.list(path)) {
          entries.forEach(CliContractTest::deleteRecursively);
        }
      }
      Files.deleteIfExists(path);
    } catch (Exception e) {
      // 清理失败不影响测试结果，记录到 stdout 供调试
      System.out.println("清理临时文件失败: " + path + " (" + e.getMessage() + ")");
    }
  }
}
