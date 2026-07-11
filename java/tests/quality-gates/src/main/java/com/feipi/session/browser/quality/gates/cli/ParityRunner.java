package com.feipi.session.browser.quality.gates.cli;

import com.feipi.session.browser.quality.gates.core.QualityGateContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.discovery.FileDiscovery;
import com.feipi.session.browser.quality.gates.rules.record.RecordComponentJavadocChecker;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 迁移一致性对比工具。
 *
 * <p>用旧 Python 和新 Java 对同一 corpus 执行检查，比较违规集合。 比较键为 {@code path|line|code|record|component}。
 */
public final class ParityRunner {

  private static final Pattern PYTHON_LINE_PATTERN = Pattern.compile("^(.+):(\\d+): (\\S+): (.+)$");

  private static final Pattern RECORD_EXTRACT =
      Pattern.compile("record ([A-Za-z_$][A-Za-z0-9_$]*)");

  private static final Pattern COMPONENT_EXTRACT =
      Pattern.compile("component ([A-Za-z_$][A-Za-z0-9_$]*)");

  private ParityRunner() {}

  /**
   * 主入口。接收两个 Python 输出文件和一个报告输出路径。
   *
   * @param args 命令行参数，依次为：fixture 目录、仓库 Java 目录、 fixture Python 输出、仓库 Python 输出、报告文件路径。
   */
  public static void main(String[] args) throws Exception {
    if (args.length < 5) {
      System.err.println(
          "Usage: ParityRunner <fixtureDir> <repoJavaDir> "
              + "<pythonFixtureOutput> <pythonRepoOutput> <reportFile>");
      System.exit(2);
    }
    var fixtureDir = Path.of(args[0]);
    var repoJavaDir = Path.of(args[1]);
    var pythonFixtureOutput = Path.of(args[2]);
    var pythonRepoOutput = Path.of(args[3]);
    var reportFile = Path.of(args[4]);

    var repoRoot = Path.of("").toAbsolutePath();
    var results = new ArrayList<String>();
    var allPassed = true;

    // 1. 比较 fixture corpus
    results.add("=== Fixture Corpus ===");
    var fixtureJavaFiles = collectJavaFiles(fixtureDir);
    var fixturePassed = compareFixture(fixtureJavaFiles, repoRoot, pythonFixtureOutput, results);
    allPassed = allPassed && fixturePassed;

    // 2. 比较真实仓库 java/ 目录
    results.add("");
    results.add("=== Real Repository (java/) ===");
    var repoPassed = compareRepo(repoJavaDir, repoRoot, pythonRepoOutput, results);
    allPassed = allPassed && repoPassed;

    // 写报告
    var parent = reportFile.getParent();
    if (parent != null) {
      Files.createDirectories(parent);
    }
    if (allPassed) {
      results.add("");
      results.add("PASSED");
    } else {
      results.add("");
      results.add("FAILED");
    }
    Files.writeString(reportFile, String.join("\n", results) + "\n", StandardCharsets.UTF_8);

    System.out.println(String.join("\n", results));
    if (!allPassed) {
      System.exit(1);
    }
  }

  private static boolean compareFixture(
      List<Path> javaFiles, Path repoRoot, Path pythonOutput, List<String> results)
      throws Exception {

    var context =
        QualityGateContext.builder()
            .repoRoot(repoRoot)
            .inputPaths(javaFiles)
            .environment(Map.of())
            .build();
    var javaViolations = RecordComponentJavadocChecker.checkFiles(javaFiles, context);
    var javaKeys = toKeys(javaViolations, repoRoot);
    var pythonKeys = parsePythonOutput(pythonOutput);

    return compareKeys(javaKeys, pythonKeys, results);
  }

  private static boolean compareRepo(
      Path repoJavaDir, Path repoRoot, Path pythonOutput, List<String> results) throws Exception {

    var context =
        QualityGateContext.builder()
            .repoRoot(repoRoot)
            .inputPaths(List.of(repoJavaDir))
            .environment(Map.of())
            .build();
    var files = FileDiscovery.discover(List.of(repoJavaDir));
    var javaViolations = RecordComponentJavadocChecker.checkFiles(files, context);
    var javaKeys = toKeys(javaViolations, repoRoot);
    var pythonKeys = parsePythonOutput(pythonOutput);

    return compareKeys(javaKeys, pythonKeys, results);
  }

  static List<String> toKeys(List<QualityViolation> violations, Path repoRoot) {
    return violations.stream().map(v -> toKey(v, repoRoot)).sorted().toList();
  }

  private static String toKey(QualityViolation v, Path repoRoot) {
    var absPath = v.path().toAbsolutePath().normalize().toString().replace('\\', '/');
    var record = v.attributes().getOrDefault("record", "");
    var component = v.attributes().getOrDefault("component", "");
    return absPath + "|" + v.line() + "|" + v.code() + "|" + record + "|" + component;
  }

  static List<String> parsePythonOutput(Path pythonOutput) throws IOException {
    if (!Files.exists(pythonOutput)) {
      return List.of();
    }
    var keys = new ArrayList<String>();
    for (var raw : Files.readAllLines(pythonOutput, StandardCharsets.UTF_8)) {
      var line = raw.trim();
      if (line.isEmpty()) {
        continue;
      }
      var matcher = PYTHON_LINE_PATTERN.matcher(line);
      if (!matcher.matches()) {
        continue;
      }
      var rawPath = matcher.group(1);
      var lineNum = matcher.group(2);
      var code = matcher.group(3);
      var message = matcher.group(4);

      var absPath = Path.of(rawPath).toAbsolutePath().normalize().toString().replace('\\', '/');
      var record = extractGroup(message, RECORD_EXTRACT);
      var component = extractGroup(message, COMPONENT_EXTRACT);

      keys.add(absPath + "|" + lineNum + "|" + code + "|" + record + "|" + component);
    }
    keys.sort(Comparator.naturalOrder());
    return keys;
  }

  private static boolean compareKeys(
      List<String> javaKeys, List<String> pythonKeys, List<String> results) {
    var javaOnly = new ArrayList<>(javaKeys);
    javaOnly.removeAll(pythonKeys);
    var pythonOnly = new ArrayList<>(pythonKeys);
    pythonOnly.removeAll(javaKeys);

    if (javaOnly.isEmpty() && pythonOnly.isEmpty()) {
      results.add("MATCH: " + javaKeys.size() + " violation(s) in both.");
      return true;
    }

    if (!javaOnly.isEmpty()) {
      results.add("ONLY IN JAVA (" + javaOnly.size() + "):");
      for (var key : javaOnly) {
        results.add("  " + key);
      }
    }
    if (!pythonOnly.isEmpty()) {
      results.add("ONLY IN PYTHON (" + pythonOnly.size() + "):");
      for (var key : pythonOnly) {
        results.add("  " + key);
      }
    }
    return false;
  }

  private static List<Path> collectJavaFiles(Path dir) throws IOException {
    if (!Files.isDirectory(dir)) {
      return List.of();
    }
    try (var stream = Files.walk(dir)) {
      return stream.filter(p -> p.toString().endsWith(".java")).sorted().toList();
    }
  }

  private static String extractGroup(String message, Pattern pattern) {
    var m = pattern.matcher(message);
    return m.find() ? m.group(1) : "";
  }
}
