package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;

/**
 * DoctorCommand 契约测试。
 *
 * <p>验证 doctor 子命令的诊断行为：help 输出、环境检查项、退出码和只读特性。
 */
@DisplayName("DoctorCommand 契约测试")
class DoctorCommandTest {

  @TempDir Path tempDir;

  /** 运行 CLI 命令并捕获输出结果。 */
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

  // ===== help 契约 =====

  @Nested
  @DisplayName("doctor --help 输出契约")
  class DoctorHelpContract {

    @Test
    @DisplayName("doctor --help 输出到 stdout，exit code = 0")
    void doctorHelpShowsOptions() {
      CliExecution result = execute("doctor", "--help");

      assertThat(result.exitCode()).isZero();
      assertThat(result.stderr()).isEmpty();
      assertThat(result.stdout()).contains("doctor");
      assertThat(result.stdout()).contains("--port");
      assertThat(result.stdout()).contains("--index-dir");
    }
  }

  // ===== 诊断项契约 =====

  @Nested
  @DisplayName("doctor 诊断输出契约")
  class DoctorOutputContract {

    @Test
    @DisplayName("doctor 输出 Java 运行时检查结果")
    void doctorShowsJavaRuntime() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("Java 运行时");
      assertThat(result.stdout()).contains("[OK]");
    }

    @Test
    @DisplayName("doctor 输出 SQLite 检查结果")
    void doctorShowsSqlite() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("SQLite");
    }

    @Test
    @DisplayName("doctor 输出数据目录检查结果")
    void doctorShowsDataDir() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("数据目录");
    }

    @Test
    @DisplayName("doctor 输出数据库检查结果")
    void doctorShowsDatabase() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("数据库");
    }

    @Test
    @DisplayName("doctor 输出 PID 文件检查结果")
    void doctorShowsPidFile() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("PID 文件");
    }

    @Test
    @DisplayName("doctor 输出诊断汇总行")
    void doctorShowsSummary() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("诊断完成");
    }
  }

  // ===== 只读契约 =====

  @Nested
  @DisplayName("doctor 只读契约")
  class DoctorReadOnlyContract {

    @Test
    @DisplayName("doctor 不在数据目录创建任何文件")
    void doctorDoesNotCreateFiles() throws Exception {
      Path dataDir = tempDir.resolve("readonly-test");
      Files.createDirectories(dataDir);

      execute("doctor", "--index-dir", dataDir.toAbsolutePath().toString(), "--port", "0");

      // doctor 不应在数据目录创建任何文件
      try (var entries = Files.list(dataDir)) {
        assertThat(entries.findFirst()).isEmpty();
      }
    }

    @Test
    @DisplayName("数据目录不存在时 doctor 仍正常完成")
    void doctorHandlesMissingDir() {
      Path missingDir = tempDir.resolve("does-not-exist");

      CliExecution result =
          execute("doctor", "--index-dir", missingDir.toAbsolutePath().toString(), "--port", "0");

      assertThat(result.stdout()).contains("首次运行时将创建");
      assertThat(result.stdout()).contains("诊断完成");
    }
  }

  // ===== 端口检查契约 =====

  @Nested
  @DisplayName("doctor 端口检查契约")
  class DoctorPortContract {

    @Test
    @DisplayName("端口为 0 时跳过端口检查")
    void portZeroSkipsCheck() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      // 端口 0 应该报告无效
      assertThat(result.stdout()).contains("端口 0");
    }
  }

  // ===== 退出码契约 =====

  @Nested
  @DisplayName("doctor 退出码契约")
  class DoctorExitCodeContract {

    @Test
    @DisplayName("所有检查通过时 exit code = 0")
    void allChecksPassExitZero() {
      CliExecution result =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "0");

      // 端口 0 报告为无效，会导致 1 项失败
      // 使用一个大概率空闲的端口确保全部通过
      CliExecution result2 =
          execute("doctor", "--index-dir", tempDir.toAbsolutePath().toString(), "--port", "19999");

      assertThat(result2.stdout()).contains("所有检查通过");
      assertThat(result2.exitCode()).isZero();
    }
  }

  // ===== 参数校验契约 =====

  @Nested
  @DisplayName("doctor 参数校验")
  class DoctorParameterContract {

    @Test
    @DisplayName("无效端口号被 Picocli 拒绝")
    void invalidPortRejected() {
      CliExecution result = execute("doctor", "--port", "abc");
      assertThat(result.exitCode()).isNotZero();
    }

    @Test
    @DisplayName("未知选项被拒绝")
    void unknownOptionRejected() {
      CliExecution result = execute("doctor", "--unknown-flag");
      assertThat(result.exitCode()).isEqualTo(2);
      assertThat(result.stderr()).contains("Unknown option");
    }
  }
}
