package com.feipi.session.browser.cli;

import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * deps 子命令实现。
 *
 * <p>产品发行包的运行时依赖已内置。本命令执行轻量 preflight，验证 Java runtime、SQLite native library 和运行时目录可写，供 shell
 * bootstrap 在构建 launcher 后确认后续 scan/serve 可运行。
 */
@Command(name = "deps", mixinStandardHelpOptions = true, description = "安装或检查项目依赖")
final class DepsCommand implements Callable<Integer> {

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  @Option(
      names = {"--index-dir"},
      description = "索引目录（默认遵循 XDG 规范）")
  private String indexDirOption;

  @Override
  public Integer call() {
    Path indexDir = PathResolver.resolveDataDir(indexDirOption, INDEX_DIR_ENV);
    RuntimePaths paths = RuntimePaths.fromDataDir(indexDir);

    List<RuntimePreflight.CheckResult> results =
        List.of(
            RuntimePreflight.checkJavaRuntime(),
            RuntimePreflight.checkSqliteNative(),
            checkRuntimePaths(paths));

    return RuntimePreflight.printResults(
        results, "依赖准备完成：产品运行时依赖已内置，可继续执行 scan 和 serve。", "依赖检查失败：");
  }

  /** 创建并验证运行时目录可写。 */
  private static RuntimePreflight.CheckResult checkRuntimePaths(RuntimePaths paths) {
    try {
      paths.ensureDirectories();
      return new RuntimePreflight.CheckResult(
          "运行时目录", true, paths.dataDir().toAbsolutePath().toString());
    } catch (Exception e) {
      return new RuntimePreflight.CheckResult("运行时目录", false, e.getMessage());
    }
  }
}
