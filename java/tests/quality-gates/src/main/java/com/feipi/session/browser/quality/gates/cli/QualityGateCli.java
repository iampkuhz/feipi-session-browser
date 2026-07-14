package com.feipi.session.browser.quality.gates.cli;

import com.feipi.session.browser.quality.gates.core.JavaSourceSet;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityGateRegistry;
import com.feipi.session.browser.quality.gates.core.QualitySummary;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.rules.JavaApiSnapshotRule;
import com.feipi.session.browser.quality.gates.rules.NoPmdSuppressionsRule;
import com.feipi.session.browser.quality.gates.rules.record.RecordComponentJavadocsRule;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/** 多规则 Java quality-gate 的唯一 CLI 入口。 */
public final class QualityGateCli {

  private QualityGateCli() {}

  /** Java 质量门禁的命令行主入口，负责接收参数并启动统一执行流程。 */
  public static void main(String[] args) {
    System.exit(run(args, System.getenv(), System.err, System.out));
  }

  /**
   * 执行聚合规则；候选只在此边界解析一次。
   *
   * @return 0=通过/不适用，1=存在违规，2=输入或执行错误。
   */
  public static int run(
      String[] args, Map<String, String> environment, PrintStream err, PrintStream out) {
    try {
      var options = Options.parse(args);
      var registry = registry();
      var unknown =
          options.rules().stream().filter(id -> !registry.registeredIds().contains(id)).toList();
      if (!unknown.isEmpty()) {
        throw new IllegalArgumentException("Unknown rules: " + unknown);
      }
      if (options.writeApiSnapshot() && !options.rules().contains("java-api-snapshot")) {
        throw new IllegalArgumentException("--write-api-snapshot requires java-api-snapshot rule");
      }
      var allCandidates = discover(options.repoRoot(), options.paths());
      var changedJson = options.changedFiles();
      if (changedJson == null) {
        changedJson = environment.get("QUALITY_CHANGED_FILES");
      }
      var candidates =
          options.rules().contains("java-api-snapshot") || changedJson == null
              ? allCandidates
              : selectChanged(options.repoRoot(), allCandidates, parseStringArray(changedJson));
      if (candidates.isEmpty()) {
        return writeSummary(options, "NOT_APPLICABLE", 0, List.of(), QualityGateExitCodes.OK, out);
      }
      var sources = JavaSourceSet.parse(options.repoRoot(), candidates);
      var context =
          new QualityContext(
              options.repoRoot(), sources, options.apiSnapshot(), options.writeApiSnapshot());
      var violations = new ArrayList<QualityViolation>();
      for (var rule : registry.select(options.rules())) {
        violations.addAll(rule.check(context));
      }
      return writeSummary(
          options,
          violations.isEmpty() ? "PASSED" : "FAILED",
          candidates.size(),
          violations,
          violations.isEmpty() ? QualityGateExitCodes.OK : QualityGateExitCodes.VIOLATIONS,
          out);
    } catch (Exception exception) {
      err.println("Java quality gates failed closed: " + exception.getMessage());
      return QualityGateExitCodes.ERROR;
    }
  }

  private static int writeSummary(
      Options options,
      String status,
      int candidateCount,
      List<QualityViolation> violations,
      int exitCode,
      PrintStream out)
      throws Exception {
    var summary = QualitySummary.json(status, candidateCount, options.rules(), violations);
    if (options.reportFile() != null) {
      var parent = options.reportFile().toAbsolutePath().getParent();
      if (parent != null) {
        Files.createDirectories(parent);
      }
      Files.writeString(options.reportFile(), summary, StandardCharsets.UTF_8);
    }
    out.print(summary);
    return exitCode;
  }

  private static List<Path> discover(Path repoRoot, List<Path> paths) throws Exception {
    var result = new LinkedHashSet<Path>();
    for (var input : paths) {
      var path = input.isAbsolute() ? input : repoRoot.resolve(input);
      path = path.toAbsolutePath().normalize();
      if (Files.isRegularFile(path) && path.toString().endsWith(".java")) {
        result.add(path);
      } else if (Files.isDirectory(path)) {
        try (var stream = Files.walk(path)) {
          stream
              .filter(Files::isRegularFile)
              .filter(file -> file.toString().endsWith(".java"))
              .filter(file -> JavaSourceSet.normalize(file).contains("/src/main/java/"))
              .filter(file -> !JavaSourceSet.normalize(file).contains("/build/"))
              .forEach(file -> result.add(file.toAbsolutePath().normalize()));
        }
      }
    }
    return result.stream().sorted().toList();
  }

  private static List<Path> selectChanged(
      Path repoRoot, List<Path> candidates, List<String> changedFiles) {
    var changed =
        changedFiles.stream()
            .map(path -> path.replace('\\', '/'))
            .map(Path::of)
            .map(path -> path.isAbsolute() ? path : repoRoot.resolve(path))
            .map(path -> path.toAbsolutePath().normalize())
            .collect(java.util.stream.Collectors.toSet());
    return candidates.stream().filter(changed::contains).toList();
  }

  private static List<String> parseStringArray(String json) {
    var values = new ArrayList<String>();
    var index = skipWhitespace(json, 0);
    if (index >= json.length() || json.charAt(index++) != '[') {
      throw new IllegalArgumentException("changed-files must be a JSON string array");
    }
    index = skipWhitespace(json, index);
    if (index < json.length() && json.charAt(index) == ']') {
      index++;
    } else {
      while (index < json.length()) {
        if (json.charAt(index++) != '"') {
          throw new IllegalArgumentException("changed-files entries must be strings");
        }
        var value = new StringBuilder();
        var closed = false;
        while (index < json.length()) {
          var character = json.charAt(index++);
          if (character == '"') {
            closed = true;
            break;
          }
          if (character == '\\') {
            if (index >= json.length()) {
              throw new IllegalArgumentException("invalid changed-files escape");
            }
            var escaped = json.charAt(index++);
            value.append(
                switch (escaped) {
                  case '"', '\\', '/' -> escaped;
                  case 'b' -> '\b';
                  case 'f' -> '\f';
                  case 'n' -> '\n';
                  case 'r' -> '\r';
                  case 't' -> '\t';
                  default -> throw new IllegalArgumentException("invalid changed-files escape");
                });
          } else {
            value.append(character);
          }
        }
        if (!closed) {
          throw new IllegalArgumentException("unterminated changed-files string");
        }
        values.add(value.toString());
        index = skipWhitespace(json, index);
        if (index < json.length() && json.charAt(index) == ',') {
          index = skipWhitespace(json, index + 1);
          continue;
        }
        if (index < json.length() && json.charAt(index) == ']') {
          index++;
          break;
        }
        throw new IllegalArgumentException("changed-files array is malformed");
      }
    }
    if (skipWhitespace(json, index) != json.length()) {
      throw new IllegalArgumentException("trailing changed-files content");
    }
    return values;
  }

  private static int skipWhitespace(String value, int start) {
    var index = start;
    while (index < value.length() && Character.isWhitespace(value.charAt(index))) {
      index++;
    }
    return index;
  }

  /** 创建所有 Java source rule 的单一 registry。 */
  public static QualityGateRegistry registry() {
    return QualityGateRegistry.builder()
        .register(new RecordComponentJavadocsRule())
        .register(new NoPmdSuppressionsRule())
        .register(new JavaApiSnapshotRule())
        .build();
  }

  /**
   * 已校验的 CLI 参数。
   *
   * @param repoRoot 仓库根目录。
   * @param paths 显式源码输入路径。
   * @param rules 待运行的规则标识列表。
   * @param changedFiles planner 传入的变更文件 JSON；未传时为空。
   * @param reportFile 结构化摘要输出文件；未传时为空。
   * @param apiSnapshot Java public API 基线文件。
   * @param writeApiSnapshot 是否显式维护 API 基线。
   */
  private record Options(
      Path repoRoot,
      List<Path> paths,
      List<String> rules,
      String changedFiles,
      Path reportFile,
      Path apiSnapshot,
      boolean writeApiSnapshot) {

    private static Options parse(String[] args) {
      var repoRoot = Path.of("").toAbsolutePath().normalize();
      var paths = new ArrayList<Path>();
      var rules = new ArrayList<String>();
      String changedFiles = null;
      Path reportFile = null;
      Path apiSnapshot = null;
      var write = false;
      for (int index = 0; index < args.length; index++) {
        switch (args[index]) {
          case "--repo-root" -> repoRoot = Path.of(requiredValue(args, ++index, "--repo-root"));
          case "--paths" -> {
            for (var value : requiredValue(args, ++index, "--paths").split(",")) {
              paths.add(Path.of(value.trim()));
            }
          }
          case "--rules" -> {
            for (var value : requiredValue(args, ++index, "--rules").split(",")) {
              if (!value.isBlank() && !rules.contains(value.trim())) {
                rules.add(value.trim());
              }
            }
          }
          case "--changed-files" -> changedFiles = requiredValue(args, ++index, "--changed-files");
          case "--report-file" ->
              reportFile = Path.of(requiredValue(args, ++index, "--report-file"));
          case "--api-snapshot" ->
              apiSnapshot = Path.of(requiredValue(args, ++index, "--api-snapshot"));
          case "--write-api-snapshot" -> write = true;
          default -> throw new IllegalArgumentException("Unknown option: " + args[index]);
        }
      }
      repoRoot = repoRoot.toAbsolutePath().normalize();
      if (rules.isEmpty()) {
        throw new IllegalArgumentException("Missing required option: --rules");
      }
      if (paths.isEmpty()) {
        paths.add(repoRoot.resolve("java"));
      }
      if (apiSnapshot == null) {
        apiSnapshot = repoRoot.resolve("config/api-snapshots/java-public-api.txt");
      } else if (!apiSnapshot.isAbsolute()) {
        apiSnapshot = repoRoot.resolve(apiSnapshot);
      }
      return new Options(
          repoRoot,
          List.copyOf(paths),
          List.copyOf(rules),
          changedFiles,
          reportFile,
          apiSnapshot,
          write);
    }

    private static String requiredValue(String[] args, int index, String option) {
      if (index >= args.length) {
        throw new IllegalArgumentException("Missing value for " + option);
      }
      return args[index];
    }
  }
}
