package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 零 Python 产品运行时门禁测试。
 *
 * <p>PR-060 GATE：验证产品发行包和运行时无 Python 依赖。 校验放置：
 *
 * <ul>
 *   <li>发行包 Python 制品扫描在 contract-tests 边界验证一次。
 *   <li>CLI 无 Python 运行在 installDist 产物边界验证一次。
 *   <li>源码 Python 调用扫描在 contract-tests 边界验证一次。
 * </ul>
 */
@DisplayName("零 Python 产品运行时门禁")
class PythonRuntimeZeroGateTest {

  /**
   * 发行包 Python 制品扫描。
   *
   * <p>验证 installDist 产物不含任何 Python 相关文件或目录。 清洁机发行包必须独立于 Python 环境。
   */
  @Nested
  @DisplayName("发行包无 Python 制品")
  class DistributionArtifactScan {

    @Test
    @DisplayName("installDist 目录不含 .py 文件")
    void noPythonFilesInInstallDist() throws IOException {
      Path installDir = findInstallDistDir();
      if (!Files.exists(installDir)) {
        return;
      }
      List<Path> pyFiles = collectFilesMatching(installDir, p -> p.toString().endsWith(".py"));
      assertThat(pyFiles).as("发行包不应包含 .py 文件，但发现: %s", pyFiles).isEmpty();
    }

    @Test
    @DisplayName("installDist 目录不含 __pycache__ 目录")
    void noPycacheInInstallDist() throws IOException {
      Path installDir = findInstallDistDir();
      if (!Files.exists(installDir)) {
        return;
      }
      List<Path> pycacheDirs =
          collectDirsMatching(installDir, p -> p.getFileName().toString().equals("__pycache__"));
      assertThat(pycacheDirs).as("发行包不应包含 __pycache__ 目录").isEmpty();
    }

    @Test
    @DisplayName("installDist 目录不含 .pyc 或 .pyo 文件")
    void noCompiledPythonInInstallDist() throws IOException {
      Path installDir = findInstallDistDir();
      if (!Files.exists(installDir)) {
        return;
      }
      List<Path> compiled =
          collectFilesMatching(
              installDir, p -> p.toString().endsWith(".pyc") || p.toString().endsWith(".pyo"));
      assertThat(compiled).as("发行包不应包含 .pyc/.pyo 文件").isEmpty();
    }

    @Test
    @DisplayName("installDist 目录不含 venv 或 site-packages 目录")
    void noVenvInInstallDist() throws IOException {
      Path installDir = findInstallDistDir();
      if (!Files.exists(installDir)) {
        return;
      }
      List<Path> venvDirs =
          collectDirsMatching(
              installDir,
              p -> {
                String name = p.getFileName().toString();
                return name.equals("venv")
                    || name.equals("site-packages")
                    || name.equals(".venv")
                    || name.equals("python3");
              });
      assertThat(venvDirs).as("发行包不应包含 venv/site-packages 目录").isEmpty();
    }

    @Test
    @DisplayName("installDist lib 目录只包含 JAR 和脚本文件")
    void onlyExpectedArtifactsInLibDir() throws IOException {
      Path libDir = findInstallDistDir().resolve("lib");
      if (!Files.exists(libDir)) {
        return;
      }
      try (Stream<Path> files = Files.list(libDir)) {
        List<Path> unexpected =
            files
                .filter(Files::isRegularFile)
                .filter(
                    p -> {
                      String name = p.getFileName().toString();
                      return !name.endsWith(".jar")
                          && !name.equals("app-cli")
                          && !name.startsWith(".");
                    })
                .toList();
        assertThat(unexpected).as("lib 目录应只包含 .jar 文件，但发现意外文件: %s", unexpected).isEmpty();
      }
    }
  }

  /**
   * CLI 无 Python 运行验证。
   *
   * <p>在 PATH 中移除 Python 后运行 CLI 命令，验证产品全功能不依赖 Python。 校验放置：CLI 独立性在 installDist 边界验证。
   */
  @Nested
  @DisplayName("CLI 无 Python 运行")
  class CliWithoutPython {

    @Test
    @DisplayName("--help 在无 Python PATH 环境下正常工作")
    void helpWithoutPythonInPath() throws Exception {
      Path binScript = findInstallDistBinScript();
      if (binScript == null) {
        return;
      }
      ProcessResult result = runCliWithoutPython(binScript, "--help");
      assertThat(result.exitCode).as("--help 退出码应为 0，stderr: %s", result.stderr).isZero();
      assertThat(result.stdout).contains("session-browser");
    }

    @Test
    @DisplayName("--version 在无 Python PATH 环境下正常工作")
    void versionWithoutPythonInPath() throws Exception {
      Path binScript = findInstallDistBinScript();
      if (binScript == null) {
        return;
      }
      ProcessResult result = runCliWithoutPython(binScript, "--version");
      assertThat(result.exitCode).as("--version 退出码应为 0，stderr: %s", result.stderr).isZero();
      assertThat(result.stdout).contains("feipi-session-browser");
    }

    @Test
    @DisplayName("status 子命令在无 Python PATH 环境下可执行")
    void statusWithoutPythonInPath() throws Exception {
      Path binScript = findInstallDistBinScript();
      if (binScript == null) {
        return;
      }
      // status 命令可能在无服务运行时返回非零，但不应因缺少 Python 而失败
      ProcessResult result = runCliWithoutPython(binScript, "status");
      // status 在无服务时返回非零是预期的，但不应该出现 python/Python 相关错误
      assertThat(result.stderr)
          .as("status 命令 stderr 不应包含 Python 相关错误")
          .doesNotContainIgnoringCase("python")
          .doesNotContainIgnoringCase("No module named");
    }

    @Test
    @DisplayName("deps 子命令在无 Python PATH 环境下正常工作")
    void depsWithoutPythonInPath() throws Exception {
      Path binScript = findInstallDistBinScript();
      if (binScript == null) {
        return;
      }
      ProcessResult result = runCliWithoutPython(binScript, "deps");
      assertThat(result.exitCode).as("deps 退出码应为 0，stderr: %s", result.stderr).isZero();
    }

    /** 在清理 PATH 的环境中运行 CLI，移除所有 Python 可执行文件路径。 */
    private ProcessResult runCliWithoutPython(Path binScript, String... args)
        throws IOException, InterruptedException {
      List<String> command = new ArrayList<>();
      command.add(binScript.toAbsolutePath().toString());
      command.addAll(List.of(args));

      // 构建不含 Python 的 PATH
      String cleanPath = buildPythonFreePath();

      ProcessBuilder pb = new ProcessBuilder(command);
      pb.environment().put("PATH", cleanPath);
      // 明确设置 PYTHONHOME 和 PYTHONPATH 为空，消除任何 Python 环境干扰
      pb.environment().put("PYTHONHOME", "");
      pb.environment().put("PYTHONPATH", "");
      pb.redirectErrorStream(false);

      Process process = pb.start();
      String stdout = readStream(process.getInputStream());
      String stderr = readStream(process.getErrorStream());
      boolean finished = process.waitFor(30, TimeUnit.SECONDS);
      if (!finished) {
        process.destroyForcibly();
        return new ProcessResult("", "进程超时", 1);
      }
      return new ProcessResult(stdout, stderr, process.exitValue());
    }

    /** 从当前 PATH 中移除可能包含 Python 的目录。 */
    private String buildPythonFreePath() {
      String currentPath = System.getenv("PATH");
      if (currentPath == null) {
        return "";
      }
      String[] dirs = currentPath.split(":");
      StringBuilder cleanPath = new StringBuilder();
      for (String dir : dirs) {
        // 保留不包含 python/conda 的 PATH 目录
        String lower = dir.toLowerCase();
        if (!lower.contains("python")
            && !lower.contains("conda")
            && !lower.contains("pyenv")
            && !lower.contains("virtualenv")) {
          if (cleanPath.length() > 0) {
            cleanPath.append(":");
          }
          cleanPath.append(dir);
        }
      }
      return cleanPath.toString();
    }
  }

  /**
   * 源码 Python 调用扫描。
   *
   * <p>验证 Java 产品源码不包含调用 Python 进程的代码。 仅允许开发质量工具（reuse-analyzer）使用 ProcessBuilder。
   */
  @Nested
  @DisplayName("源码无 Python 进程调用")
  class SourceCodePythonInvocationScan {

    @Test
    @DisplayName("app-cli 模块不通过 ProcessBuilder 调用 Python")
    void appCliNoPythonProcessBuilder() throws IOException {
      Path appCliSrc = findProjectRoot().resolve("java/app-cli/src/main/java");
      if (!Files.exists(appCliSrc)) {
        return;
      }
      assertNoPythonInvocation(appCliSrc);
    }

    @Test
    @DisplayName("application 模块不通过 ProcessBuilder 调用 Python")
    void applicationNoPythonProcessBuilder() throws IOException {
      Path src = findProjectRoot().resolve("java/application/src/main/java");
      if (!Files.exists(src)) {
        return;
      }
      assertNoPythonInvocation(src);
    }

    @Test
    @DisplayName("web 模块不通过 ProcessBuilder 调用 Python")
    void webNoPythonProcessBuilder() throws IOException {
      Path src = findProjectRoot().resolve("java/web/src/main/java");
      if (!Files.exists(src)) {
        return;
      }
      assertNoPythonInvocation(src);
    }

    @Test
    @DisplayName("scan-engine 模块不通过 ProcessBuilder 调用 Python")
    void scanEngineNoPythonProcessBuilder() throws IOException {
      Path src = findProjectRoot().resolve("java/scan-engine/src/main/java");
      if (!Files.exists(src)) {
        return;
      }
      assertNoPythonInvocation(src);
    }

    @Test
    @DisplayName("index-sqlite 模块不通过 ProcessBuilder 调用 Python")
    void indexSqliteNoPythonProcessBuilder() throws IOException {
      Path src = findProjectRoot().resolve("java/index-sqlite/src/main/java");
      if (!Files.exists(src)) {
        return;
      }
      assertNoPythonInvocation(src);
    }

    @Test
    @DisplayName("normalization-engine 模块不通过 ProcessBuilder 调用 Python")
    void normalizationEngineNoPythonProcessBuilder() throws IOException {
      Path src = findProjectRoot().resolve("java/normalization-engine/src/main/java");
      if (!Files.exists(src)) {
        return;
      }
      assertNoPythonInvocation(src);
    }

    @Test
    @DisplayName("所有 source adapter 模块不通过 ProcessBuilder 调用 Python")
    void sourceAdaptersNoPythonProcessBuilder() throws IOException {
      Path projectRoot = findProjectRoot();
      List<String> sourceModules =
          List.of("source-spi", "source-json", "source-claude", "source-codex", "source-qoder");
      for (String mod : sourceModules) {
        Path src = projectRoot.resolve("java/" + mod + "/src/main/java");
        if (Files.exists(src)) {
          assertNoPythonInvocation(src);
        }
      }
    }

    /**
     * 验证源码目录不含 Python 进程调用模式。 检测 {@code ProcessBuilder("python"...)} 和 {@code
     * Runtime.getRuntime().exec("python"...)}。
     */
    private void assertNoPythonInvocation(Path srcDir) throws IOException {
      try (Stream<Path> walk = Files.walk(srcDir)) {
        List<String> violations =
            walk.filter(p -> p.toString().endsWith(".java"))
                .filter(Files::isRegularFile)
                .flatMap(
                    p -> {
                      try {
                        List<String> lines = Files.readAllLines(p);
                        List<String> result = new ArrayList<>();
                        for (int i = 0; i < lines.size(); i++) {
                          String line = lines.get(i);
                          String trimmed = line.trim();
                          // 跳过注释行
                          if (trimmed.startsWith("//")
                              || trimmed.startsWith("*")
                              || trimmed.startsWith("/*")) {
                            continue;
                          }
                          if (containsPythonInvocation(line)) {
                            result.add(p.getFileName() + ":" + (i + 1) + " -> " + trimmed);
                          }
                        }
                        return result.stream();
                      } catch (IOException e) {
                        return Stream.empty();
                      }
                    })
                .toList();
        assertThat(violations).as("产品源码不应包含 Python 进程调用，但发现: %s", violations).isEmpty();
      }
    }

    /** 检查代码行是否包含 Python 进程调用模式。 匹配 ProcessBuilder/Runtime.exec 与 python/python3 参数的组合。 */
    private boolean containsPythonInvocation(String line) {
      String lower = line.toLowerCase();
      boolean hasProcessCreation =
          lower.contains("processbuilder")
              || lower.contains("runtime.getruntime().exec")
              || lower.contains(".exec(");
      boolean hasPythonArg =
          lower.contains("\"python")
              || lower.contains("\"python3\"")
              || lower.contains("python ")
              || lower.contains("\"pip\"")
              || lower.contains("\"pip3\"");
      return hasProcessCreation && hasPythonArg;
    }
  }

  /**
   * 开发工具 Python 边界验证。
   *
   * <p>验证剩余 Python 文件仅存在于开发质量工具目录（scripts/quality、scripts/qa 等）， 不在产品运行链中。
   */
  @Nested
  @DisplayName("开发工具 Python 边界")
  class DevToolPythonBoundary {

    @Test
    @DisplayName("Python 文件仅存在于允许的开发工具目录或待清理的遗留源码目录")
    void pythonFilesOnlyInAllowedDirectories() throws IOException {
      Path projectRoot = findProjectRoot();
      List<Path> pythonFiles;
      try (Stream<Path> walk = Files.walk(projectRoot)) {
        pythonFiles =
            walk.filter(Files::isRegularFile)
                .filter(p -> p.toString().endsWith(".py"))
                // 排除 .git、tmp、build 目录
                .filter(
                    p -> {
                      String rel = projectRoot.relativize(p).toString();
                      return !rel.startsWith(".git")
                          && !rel.startsWith("tmp")
                          && !rel.contains("/build/")
                          && !rel.contains("__pycache__");
                    })
                .toList();
      }

      // 每个 Python 文件必须在允许的开发工具目录中，或在待清理的遗留 src/ 目录中
      List<String> allowedPrefixes =
          List.of(
              "scripts/quality/",
              "scripts/qa/",
              "scripts/claude_hooks/",
              "scripts/agent_hooks/",
              "scripts/harness/",
              "scripts/openspec/",
              "scripts/hooks/",
              "scripts/check_",
              "scripts/start_",
              "scripts/generate_",
              "scripts/validate_",
              "tests/",
              "tmp/",
              // 遗留 Python 产品源码，PR-020/PR-030 清理中
              "src/session_browser/");

      for (Path pyFile : pythonFiles) {
        String rel = projectRoot.relativize(pyFile).toString();
        boolean inAllowedDir = allowedPrefixes.stream().anyMatch(rel::startsWith);
        assertThat(inAllowedDir).as("Python 文件 %s 应仅存在于允许的开发工具目录中", rel).isTrue();
      }
    }

    @Test
    @DisplayName("PR-020/PR-030 已删除的 Python 子目录不再包含产品运行代码")
    void pythonProductSubdirectoriesCleaned() throws IOException {
      Path pythonSrc = findProjectRoot().resolve("src/session_browser");
      if (!Files.exists(pythonSrc)) {
        return; // 目录已完全移除，迁移完成
      }
      // PR-020/PR-030 应已清理的子目录
      List<String> removedSubdirs = List.of("index", "normalized", "sources");
      for (String subdir : removedSubdirs) {
        Path sub = pythonSrc.resolve(subdir);
        if (Files.exists(sub)) {
          try (Stream<Path> walk = Files.walk(sub)) {
            long pyCount = walk.filter(p -> p.toString().endsWith(".py")).count();
            assertThat(pyCount).as("src/session_browser/%s 应已被 PR-020/PR-030 清理", subdir).isZero();
          }
        }
      }
    }

    @Test
    @DisplayName("requirements.txt 和 pyproject.toml 运行时依赖已清理")
    void noPythonRuntimeDependencies() throws IOException {
      Path projectRoot = findProjectRoot();
      Path requirements = projectRoot.resolve("requirements.txt");
      if (Files.exists(requirements)) {
        List<String> lines = Files.readAllLines(requirements);
        // 检查是否仍有运行时依赖（flask, fastapi, django 等）
        List<String> runtimeDeps =
            lines.stream()
                .filter(l -> !l.trim().isEmpty() && !l.trim().startsWith("#"))
                .filter(
                    l -> {
                      String lower = l.toLowerCase();
                      return lower.contains("flask")
                          || lower.contains("fastapi")
                          || lower.contains("django")
                          || lower.contains("requests")
                          || lower.contains("aiohttp")
                          || lower.contains("sqlalchemy");
                    })
                .toList();
        assertThat(runtimeDeps).as("requirements.txt 不应包含运行时 Python 依赖").isEmpty();
      }
    }
  }

  // ===== 辅助方法和类型 =====

  private record ProcessResult(String stdout, String stderr, int exitCode) {}

  private static Path findProjectRoot() {
    Path dir = Path.of(System.getProperty("user.dir"));
    while (dir != null) {
      if (Files.exists(dir.resolve("settings.gradle.kts"))) {
        return dir;
      }
      dir = dir.getParent();
    }
    return Path.of(System.getProperty("user.dir"));
  }

  private static Path findInstallDistDir() {
    return findProjectRoot().resolve("java/app-cli/build/install/app-cli");
  }

  private static Path findInstallDistBinScript() {
    Path bin = findInstallDistDir().resolve("bin/app-cli");
    return Files.exists(bin) ? bin : null;
  }

  private interface PathPredicate {
    boolean test(Path p);
  }

  private List<Path> collectFilesMatching(Path root, PathPredicate predicate) throws IOException {
    try (Stream<Path> walk = Files.walk(root)) {
      return walk.filter(Files::isRegularFile).filter(predicate::test).toList();
    }
  }

  private List<Path> collectDirsMatching(Path root, PathPredicate predicate) throws IOException {
    try (Stream<Path> walk = Files.walk(root)) {
      return walk.filter(Files::isDirectory).filter(predicate::test).toList();
    }
  }

  private String readStream(java.io.InputStream is) throws IOException {
    try (BufferedReader reader = new BufferedReader(new InputStreamReader(is))) {
      StringBuilder sb = new StringBuilder();
      String line;
      while ((line = reader.readLine()) != null) {
        sb.append(line).append("\n");
      }
      return sb.toString();
    }
  }
}
