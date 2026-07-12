package com.feipi.session.browser.cli;

import com.feipi.session.browser.cli.diagnose.DiagnoseOutputModel;
import com.feipi.session.browser.cli.diagnose.DiagnosePipeline;
import com.feipi.session.browser.cli.diagnose.HumanRenderer;
import com.feipi.session.browser.cli.diagnose.JsonRenderer;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * diagnose session 子命令。
 *
 * <p>一次命令输出 source/raw/normalization/projection/divergence 五部分诊断信息， 替代多次 find/grep/curl/python3 探测。
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 成功，无 mismatch
 *   <li>1 — 发现至少一个 mismatch
 *   <li>2 — 输入/数据错误
 *   <li>3 — 内部错误
 * </ul>
 */
@Command(
    name = "session",
    mixinStandardHelpOptions = true,
    description = "诊断指定 session 的数据管道各层状态",
    sortOptions = false)
final class DiagnoseSessionCommand implements Callable<Integer> {

  /** 环境变量：Claude 数据根目录。 */
  private static final String CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR";

  @Option(
      names = {"--agent"},
      required = true,
      description = "agent 类型（如 claude_code, codex, qoder）")
  private String agent;

  @Option(
      names = {"--session-id"},
      required = true,
      description = "目标 session UUID")
  private String sessionId;

  @Option(
      names = {"--format", "-f"},
      defaultValue = "text",
      description = "输出格式：text（默认）或 json")
  private String format;

  @Option(
      names = {"--source-dir"},
      description = "agent 数据源根目录（默认从环境变量或平台默认路径推断）")
  private String sourceDirOption;

  @Option(
      names = {"--verbose", "-v"},
      description = "显示更多细节")
  private boolean verbose;

  @Override
  public Integer call() {
    // 验证 agent 参数
    if (agent == null || agent.isBlank()) {
      System.err.println("错误: --agent 不得为空");
      return 2;
    }

    // 验证 sessionId 参数
    if (sessionId == null || sessionId.isBlank()) {
      System.err.println("错误: --session-id 不得为空");
      return 2;
    }

    // 解析 source root
    Path sourceRoot = resolveSourceRoot();
    if (sourceRoot == null) {
      System.err.println("错误: 无法确定 agent 数据源目录，请使用 --source-dir 指定");
      return 2;
    }

    try {
      DiagnoseOutputModel.DiagnoseOutput output =
          DiagnosePipeline.run(agent, sessionId, sourceRoot);

      // 渲染输出
      String rendered;
      if ("json".equalsIgnoreCase(format)) {
        rendered = JsonRenderer.render(output);
      } else {
        rendered = HumanRenderer.render(output);
      }
      System.out.println(rendered);

      // 退出码：mismatch → 1，source error → 2
      return resolveExitCode(output);
    } catch (Exception e) {
      System.err.println("内部错误: " + e.getMessage());
      return 3;
    }
  }

  private Path resolveSourceRoot() {
    if (sourceDirOption != null && !sourceDirOption.isBlank()) {
      return Path.of(PathUtils.expandTilde(sourceDirOption));
    }

    // 环境变量
    String envValue = System.getenv(CLAUDE_CONFIG_DIR_ENV);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }

    // 默认 Claude 目录
    String home = System.getProperty("user.home");
    if (home == null || home.isBlank()) {
      return null;
    }

    String agentLower = agent.toLowerCase().replace('-', '_');
    return switch (agentLower) {
      case "claude_code" -> Path.of(home, ".claude");
      case "codex" -> Path.of(home, ".codex");
      case "qoder" -> Path.of(home, ".qoder");
      default -> null;
    };
  }

  private static int resolveExitCode(DiagnoseOutputModel.DiagnoseOutput output) {
    // source 层错误 → 2
    if ("ERROR".equals(output.source().status())) {
      return 2;
    }
    // 存在分歧 → 1
    if ("MISMATCH".equals(output.divergence().status())) {
      return 1;
    }
    return 0;
  }
}
