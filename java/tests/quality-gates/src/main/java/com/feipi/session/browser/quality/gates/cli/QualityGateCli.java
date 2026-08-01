package com.feipi.session.browser.quality.gates.cli;

import com.feipi.session.browser.quality.gates.core.AdvisoryQualityRule;
import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule;
import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule.BaselineUpdate;
import com.feipi.session.browser.quality.gates.core.JavaSourceSet;
import com.feipi.session.browser.quality.gates.core.QualityAdvisory;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityGateRegistry;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualitySummary;
import com.feipi.session.browser.quality.gates.core.QualitySummary.RuleExecution;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.core.RepositorySourceSet;
import com.feipi.session.browser.quality.gates.rules.JavaApiSnapshotRule;
import com.feipi.session.browser.quality.gates.rules.JavaCommentLanguageRule;
import com.feipi.session.browser.quality.gates.rules.NoPmdSuppressionsRule;
import com.feipi.session.browser.quality.gates.rules.TemplateContractRule;
import com.feipi.session.browser.quality.gates.rules.record.RecordComponentJavadocsRule;
import com.feipi.session.browser.quality.gates.rules.web.CssOwnershipRule;
import com.feipi.session.browser.quality.gates.rules.web.LayoutInlineStyleRule;
import com.feipi.session.browser.quality.gates.rules.web.RawInnerHtmlRule;
import com.feipi.session.browser.quality.gates.rules.web.StaticResourceContractRule;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

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
      var unknownUpdates =
          options.baselineUpdateRules().stream()
              .filter(id -> !registry.registeredIds().contains(id))
              .toList();
      if (!unknownUpdates.isEmpty()) {
        throw new IllegalArgumentException("Unknown baseline update rules: " + unknownUpdates);
      }
      if (options.writeApiSnapshot() && !options.rules().contains("java-api-snapshot")) {
        throw new IllegalArgumentException("--write-api-snapshot requires java-api-snapshot rule");
      }
      if (options.baselineUpdateRequested()) {
        if (!new LinkedHashSet<>(options.rules())
            .equals(new LinkedHashSet<>(options.baselineUpdateRules()))) {
          throw new IllegalArgumentException("--update-baselines must exactly match --rules");
        }
        if (options.writeApiSnapshot()) {
          throw new IllegalArgumentException(
              "--update-baselines cannot be combined with --write-api-snapshot");
        }
      }
      var selectedRules = registry.select(options.rules());
      var needsQualityArtifacts =
          selectedRules.stream().anyMatch(CssOwnershipRule.class::isInstance);
      var selectedUpdaters =
          options.baselineUpdateRequested()
              ? requireBaselineUpdaters(selectedRules)
              : List.<BaselineUpdatableRule>of();
      var allSources =
          RepositorySourceSet.discover(
              options.repoRoot(),
              options.paths(),
              path -> selectedRules.stream().anyMatch(rule -> rule.supportsPath(path)));
      var changedJson = options.changedFiles();
      if (changedJson == null) {
        changedJson = environment.get("QUALITY_CHANGED_FILES");
      }
      var changedPaths =
          changedJson != null && selectedRules.stream().anyMatch(QualityRule::usesChangedFiles)
              ? changedPaths(options.repoRoot(), parseStringArray(changedJson))
              : null;
      var sourcesByRule = new LinkedHashMap<String, RepositorySourceSet>();
      var requiredInputsByRule = new LinkedHashMap<String, List<Path>>();
      var candidateIndex = new LinkedHashMap<Path, RepositorySourceSet.SourceText>();
      var candidatePaths = new LinkedHashSet<Path>();
      for (var rule : selectedRules) {
        var ruleSources = selectForRule(allSources, rule, changedPaths);
        var requiredInputs = requiredInputs(options.repoRoot(), rule);
        sourcesByRule.put(rule.id(), ruleSources);
        requiredInputsByRule.put(rule.id(), requiredInputs);
        for (var source : ruleSources.sources()) {
          candidateIndex.put(source.path(), source);
          candidatePaths.add(source.path());
        }
        candidatePaths.addAll(requiredInputs);
      }
      var repositorySources =
          new RepositorySourceSet(
              candidateIndex.values().stream()
                  .sorted(Comparator.comparing(RepositorySourceSet.SourceText::relativePath))
                  .toList());
      var javaCandidates =
          repositorySources.sources().stream()
              .filter(source -> source.relativePath().endsWith(".java"))
              .map(RepositorySourceSet.SourceText::path)
              .toList();
      // 纯 Kotlin 批次不启动空 javac task；Java 规则不会收到这批候选。
      var sources =
          javaCandidates.isEmpty()
              ? new JavaSourceSet(List.of(), null)
              : JavaSourceSet.parse(options.repoRoot(), javaCandidates);
      var context =
          new QualityContext(
              options.repoRoot(),
              sources,
              repositorySources,
              options.apiSnapshot(),
              options.writeApiSnapshot(),
              qualityArtifactDirectory(options.repoRoot(), environment, needsQualityArtifacts));
      if (options.baselineUpdateRequested()) {
        return updateBaselines(
            options,
            selectedUpdaters,
            sourcesByRule,
            requiredInputsByRule,
            candidatePaths,
            context,
            out);
      }
      if (candidatePaths.isEmpty()) {
        var executions =
            selectedRules.stream().map(rule -> new RuleExecution(rule.id(), 0, List.of())).toList();
        return writeSummary(options, 0, executions, QualityGateExitCodes.OK, out);
      }
      var executions = new ArrayList<RuleExecution>();
      for (var rule : selectedRules) {
        var ruleSources = sourcesByRule.get(rule.id());
        var ruleCandidates = new LinkedHashSet<Path>();
        ruleSources.sources().stream()
            .map(RepositorySourceSet.SourceText::path)
            .forEach(ruleCandidates::add);
        ruleCandidates.addAll(requiredInputsByRule.get(rule.id()));
        var violations = List.<QualityViolation>of();
        var advisories = List.<QualityAdvisory>of();
        if (!ruleCandidates.isEmpty()) {
          var ruleContext = contextForRule(context, ruleSources);
          if (rule instanceof AdvisoryQualityRule advisoryRule) {
            var evaluation = advisoryRule.evaluate(ruleContext);
            violations = evaluation.violations();
            advisories = evaluation.advisories();
          } else {
            violations = rule.check(ruleContext);
          }
        }
        executions.add(new RuleExecution(rule.id(), ruleCandidates.size(), violations, advisories));
      }
      var hasViolations = executions.stream().anyMatch(item -> !item.violations().isEmpty());
      return writeSummary(
          options,
          candidatePaths.size(),
          executions,
          hasViolations ? QualityGateExitCodes.VIOLATIONS : QualityGateExitCodes.OK,
          out);
    } catch (Exception exception) {
      err.println("Java quality gates failed closed: " + exception.getMessage());
      return QualityGateExitCodes.ERROR;
    }
  }

  private static int updateBaselines(
      Options options,
      List<BaselineUpdatableRule> selectedRules,
      Map<String, RepositorySourceSet> sourcesByRule,
      Map<String, List<Path>> requiredInputsByRule,
      Set<Path> candidatePaths,
      QualityContext context,
      PrintStream out)
      throws Exception {
    var updatesByPath =
        new java.util.TreeMap<Path, Map<String, Map<String, List<String>>>>(
            Comparator.comparing(Path::toString));
    var executions = new ArrayList<RuleExecution>();
    for (var rule : selectedRules) {
      var ruleSources = sourcesByRule.get(rule.id());
      var ruleContext = contextForRule(context, ruleSources);
      var update = rule.baselineUpdate(ruleContext);
      var path = normalizedBaselinePath(options.repoRoot(), update);
      candidatePaths.add(path);
      var sections = updatesByPath.computeIfAbsent(path, ignored -> new LinkedHashMap<>());
      sections.put(rule.id(), update.section());

      var ruleCandidates = new LinkedHashSet<Path>();
      ruleSources.sources().stream()
          .map(RepositorySourceSet.SourceText::path)
          .forEach(ruleCandidates::add);
      ruleCandidates.addAll(requiredInputsByRule.get(rule.id()));
      ruleCandidates.add(path);
      executions.add(new RuleExecution(rule.id(), ruleCandidates.size(), List.of()));
    }
    for (var update : updatesByPath.entrySet()) {
      BaselineUpdateWriter.mergeAndWrite(update.getKey(), update.getValue());
    }
    return writeSummary(options, candidatePaths.size(), executions, QualityGateExitCodes.OK, out);
  }

  private static List<BaselineUpdatableRule> requireBaselineUpdaters(
      List<QualityRule> selectedRules) {
    var updaters = new ArrayList<BaselineUpdatableRule>();
    for (var rule : selectedRules) {
      if (!(rule instanceof BaselineUpdatableRule updater)) {
        throw new IllegalArgumentException("Rule does not support baseline updates: " + rule.id());
      }
      updaters.add(updater);
    }
    return List.copyOf(updaters);
  }

  private static Path normalizedBaselinePath(Path repoRoot, BaselineUpdate update) {
    var root = repoRoot.toAbsolutePath().normalize();
    var path = update.path().isAbsolute() ? update.path() : root.resolve(update.path());
    path = path.toAbsolutePath().normalize();
    if (!path.startsWith(root)) {
      throw new IllegalArgumentException("baseline update escapes repository: " + path);
    }
    return path;
  }

  private static QualityContext contextForRule(
      QualityContext context, RepositorySourceSet repositorySources) {
    var selectedPaths =
        repositorySources.sources().stream()
            .map(RepositorySourceSet.SourceText::path)
            .collect(java.util.stream.Collectors.toSet());
    var javaSources =
        context.sources().sources().stream()
            .filter(source -> selectedPaths.contains(source.path()))
            .toList();
    return new QualityContext(
        context.repoRoot(),
        new JavaSourceSet(javaSources, context.sources().docTrees()),
        repositorySources,
        context.apiSnapshot(),
        context.writeApiSnapshot(),
        context.qualityArtifactDir());
  }

  private static Path qualityArtifactDirectory(
      Path repoRoot, Map<String, String> environment, boolean required) {
    var normalizedRoot = repoRoot.toAbsolutePath().normalize();
    var directFallback =
        normalizedRoot.resolve("tmp/quality/direct/pid-" + ProcessHandle.current().pid());
    if (!required) {
      // 当前只有 CSS ownership 产出该目录；其他聚合规则不解析与自身无关的环境变量。
      return directFallback;
    }
    var configured = environment.get("FEIPI_QUALITY_ARTIFACT_DIR");
    if (configured == null || configured.isBlank()) {
      return requireRepoLocalArtifactDirectory(normalizedRoot, directFallback);
    }
    var path = Path.of(configured);
    if (!path.isAbsolute()) {
      throw new IllegalArgumentException("FEIPI_QUALITY_ARTIFACT_DIR must be absolute");
    }
    return requireRepoLocalArtifactDirectory(normalizedRoot, path.toAbsolutePath().normalize());
  }

  private static Path requireRepoLocalArtifactDirectory(Path repoRoot, Path candidate) {
    var qualityRoot = repoRoot.resolve("tmp/quality").normalize();
    if (!candidate.startsWith(qualityRoot)) {
      throw new IllegalArgumentException(
          "FEIPI_QUALITY_ARTIFACT_DIR must stay within " + qualityRoot);
    }
    var current = repoRoot;
    for (var component : repoRoot.relativize(candidate)) {
      current = current.resolve(component);
      if (Files.isSymbolicLink(current)) {
        throw new IllegalArgumentException(
            "FEIPI_QUALITY_ARTIFACT_DIR contains symbolic link: " + current);
      }
    }
    return candidate;
  }

  private static int writeSummary(
      Options options,
      int candidateCount,
      List<RuleExecution> executions,
      int exitCode,
      PrintStream out)
      throws Exception {
    var summary = QualitySummary.json(candidateCount, executions);
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

  private static Set<Path> changedPaths(Path repoRoot, List<String> changedFiles) {
    return changedFiles.stream()
        .map(path -> path.replace('\\', '/'))
        .map(Path::of)
        .map(path -> path.isAbsolute() ? path : repoRoot.resolve(path))
        .map(path -> path.toAbsolutePath().normalize())
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
  }

  private static RepositorySourceSet selectForRule(
      RepositorySourceSet sources, QualityRule rule, Set<Path> changedPaths) {
    var selected =
        sources.sources().stream()
            .filter(source -> rule.supportsPath(source.relativePath()))
            .filter(
                source ->
                    changedPaths == null
                        || !rule.usesChangedFiles()
                        || changedPaths.contains(source.path()))
            .toList();
    return new RepositorySourceSet(selected);
  }

  private static List<Path> requiredInputs(Path repoRoot, QualityRule rule) {
    var normalizedRoot = repoRoot.toAbsolutePath().normalize();
    var result = new LinkedHashSet<Path>();
    for (var input : rule.requiredInputs(normalizedRoot)) {
      var path = input.isAbsolute() ? input : normalizedRoot.resolve(input);
      path = path.toAbsolutePath().normalize();
      if (!path.startsWith(normalizedRoot)) {
        throw new IllegalArgumentException("required input escapes repository: " + path);
      }
      result.add(path);
    }
    return List.copyOf(result);
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
        .register(new JavaCommentLanguageRule())
        .register(new TemplateContractRule())
        .register(new StaticResourceContractRule())
        .register(new RawInnerHtmlRule())
        .register(new LayoutInlineStyleRule())
        .register(new CssOwnershipRule())
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
   * @param baselineUpdateRequested 是否出现 baseline 维护 option。
   * @param baselineUpdateRules 显式维护 baseline 的 rule id 集合。
   */
  private record Options(
      Path repoRoot,
      List<Path> paths,
      List<String> rules,
      String changedFiles,
      Path reportFile,
      Path apiSnapshot,
      boolean writeApiSnapshot,
      boolean baselineUpdateRequested,
      List<String> baselineUpdateRules) {

    private static Options parse(String[] args) {
      var repoRoot = Path.of("").toAbsolutePath().normalize();
      var paths = new ArrayList<Path>();
      var rules = new ArrayList<String>();
      String changedFiles = null;
      Path reportFile = null;
      Path apiSnapshot = null;
      var write = false;
      var baselineUpdateRequested = false;
      var baselineUpdateRules = new ArrayList<String>();
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
          case "--update-baselines" -> {
            if (baselineUpdateRequested) {
              throw new IllegalArgumentException("--update-baselines may only be specified once");
            }
            baselineUpdateRequested = true;
            for (var value : requiredValue(args, ++index, "--update-baselines").split(",")) {
              if (!value.isBlank() && !baselineUpdateRules.contains(value.trim())) {
                baselineUpdateRules.add(value.trim());
              }
            }
          }
          default -> throw new IllegalArgumentException("Unknown option: " + args[index]);
        }
      }
      repoRoot = repoRoot.toAbsolutePath().normalize();
      if (rules.isEmpty()) {
        throw new IllegalArgumentException("Missing required option: --rules");
      }
      if (baselineUpdateRequested && baselineUpdateRules.isEmpty()) {
        throw new IllegalArgumentException("--update-baselines requires at least one rule");
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
          write,
          baselineUpdateRequested,
          List.copyOf(baselineUpdateRules));
    }

    private static String requiredValue(String[] args, int index, String option) {
      if (index >= args.length) {
        throw new IllegalArgumentException("Missing value for " + option);
      }
      return args[index];
    }
  }
}
