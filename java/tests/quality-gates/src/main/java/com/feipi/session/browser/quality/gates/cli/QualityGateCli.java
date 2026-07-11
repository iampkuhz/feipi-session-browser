package com.feipi.session.browser.quality.gates.cli;

import com.feipi.session.browser.quality.gates.core.QualityGateContext;
import com.feipi.session.browser.quality.gates.core.QualityGateRegistry;
import com.feipi.session.browser.quality.gates.core.ViolationReporter;
import com.feipi.session.browser.quality.gates.rules.record.RecordComponentJavadocGate;
import java.io.PrintStream;
import java.nio.file.Path;
import java.util.ArrayList;

/**
 * 质量门 CLI 入口。
 *
 * <p>支持参数：
 *
 * <ul>
 *   <li>{@code --gate <id>} 门禁 id（必需）。
 *   <li>{@code --repo-root <path>} 仓库根目录（默认当前目录）。
 *   <li>{@code --paths <path>} 输入路径，可重复（默认 {@code java}）。
 *   <li>{@code --files-from <path>} 从文件读取待检查路径列表。
 *   <li>{@code --format text|json} 输出格式（默认 text）。
 *   <li>{@code --report-file <path>} 报告文件路径。
 * </ul>
 */
public final class QualityGateCli {

  private QualityGateCli() {}

  /**
   * CLI 主入口。
   *
   * @param args 命令行参数。
   */
  public static void main(String[] args) {
    System.exit(run(args, System.err, System.out));
  }

  /**
   * 可测试的 CLI 执行方法。
   *
   * @param args 命令行参数。
   * @param err 错误输出流。
   * @param out 标准输出流。
   * @return 退出码。
   */
  public static int run(String[] args, PrintStream err, PrintStream out) {
    String gateId = null;
    Path repoRoot = Path.of("").toAbsolutePath();
    var inputPaths = new ArrayList<Path>();
    Path filesFrom = null;
    String format = "text";
    Path reportFile = null;

    for (int i = 0; i < args.length; i++) {
      switch (args[i]) {
        case "--gate" -> {
          if (++i < args.length) {
            gateId = args[i];
          }
        }
        case "--repo-root" -> {
          if (++i < args.length) {
            repoRoot = Path.of(args[i]);
          }
        }
        case "--paths" -> {
          if (++i < args.length) {
            for (var segment : args[i].split(",")) {
              inputPaths.add(Path.of(segment.trim()));
            }
          }
        }
        case "--files-from" -> {
          if (++i < args.length) {
            filesFrom = Path.of(args[i]);
          }
        }
        case "--format" -> {
          if (++i < args.length) {
            format = args[i];
          }
        }
        case "--report-file" -> {
          if (++i < args.length) {
            reportFile = Path.of(args[i]);
          }
        }
        case "--help", "-h" -> {
          err.println(
              "Usage: quality-gate --gate <id> [--repo-root <path>] "
                  + "[--paths <path>] [--files-from <path>] "
                  + "[--format text|json] [--report-file <path>]");
          return QualityGateExitCodes.OK;
        }
        default -> {
          err.println("Unknown option: " + args[i]);
          return QualityGateExitCodes.ERROR;
        }
      }
    }

    if (gateId == null) {
      err.println("Missing required option: --gate");
      return QualityGateExitCodes.ERROR;
    }

    if (!"text".equals(format) && !"json".equals(format)) {
      err.println("Unknown format: " + format + " (expected text or json)");
      return QualityGateExitCodes.ERROR;
    }

    var registry = createRegistry();
    var gateOpt = registry.find(gateId);
    if (gateOpt.isEmpty()) {
      err.println("gate not implemented in Batch 1: " + gateId);
      return QualityGateExitCodes.ERROR;
    }

    var gate = gateOpt.get();

    if (inputPaths.isEmpty()) {
      inputPaths.add(repoRoot.resolve("java"));
    }

    try {
      var context =
          QualityGateContext.builder()
              .repoRoot(repoRoot)
              .inputPaths(inputPaths)
              .filesFrom(filesFrom)
              .reportFile(reportFile)
              .format(format)
              .environment(System.getenv())
              .build();

      var violations = gate.check(context);

      var output =
          "json".equals(format)
              ? ViolationReporter.formatJson(violations)
              : ViolationReporter.formatText(violations);

      if (violations.isEmpty()) {
        out.print("PASSED\n");
      } else {
        err.print(output);
      }

      if (reportFile != null) {
        ViolationReporter.writeReport(violations, reportFile, format);
      }

      return violations.isEmpty() ? QualityGateExitCodes.OK : QualityGateExitCodes.VIOLATIONS;
    } catch (Exception e) {
      err.println("Internal error: " + e.getMessage());
      return QualityGateExitCodes.ERROR;
    }
  }

  /**
   * 创建包含所有已注册门禁的注册表。
   *
   * @return 质量门注册表。
   */
  public static QualityGateRegistry createRegistry() {
    return QualityGateRegistry.builder().register(new RecordComponentJavadocGate()).build();
  }
}
