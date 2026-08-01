package com.feipi.session.browser.quality.gates.rules.web;

import com.feipi.session.browser.quality.gates.core.AdvisoryQualityRule;
import com.feipi.session.browser.quality.gates.core.QualityAdvisory;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** 检查顶层 CSS 文件的分层所有权，并把完整 BLOCK/提示报告写入当前执行产物目录。 */
public final class CssOwnershipRule implements AdvisoryQualityRule {

  private static final String ID = "css-ownership";
  private static final String CSS_ROOT = "java/web/src/main/resources/static/css";
  private static final Set<String> LOW_LEVEL_FILES =
      Set.of("tokens.css", "base.css", "shell.css", "ui-primitives.css");
  private static final Set<String> GLOBAL_COMPONENTS =
      Set.of(
          ".btn",
          ".ui-btn",
          ".icon-btn",
          ".icon-button",
          ".badge",
          ".card",
          ".section",
          ".section-head",
          ".metric-card",
          ".metric-grid",
          ".tooltip",
          ".popover",
          ".menu-popover",
          ".data-table",
          ".filter-card",
          ".filter-chip",
          ".pagination",
          ".modal",
          ".payload-modal",
          ".state-strip",
          ".toast",
          ".page-head",
          ".tabs",
          ".tab-nav",
          ".tab-btn",
          ".pill",
          ".avatar");
  private static final Set<String> SAFE_COLORS = Set.of("#000", "#000000", "#fff", "#ffffff");
  private static final List<Pattern> PAGE_PATTERNS =
      patterns(
          "\\.sessions-page\\b",
          "\\.session-detail-page\\b",
          "\\.dashboard-page\\b",
          "\\.projects-page\\b",
          "\\.agents-page\\b",
          "\\.glossary-page\\b");
  private static final List<Pattern> PRIMITIVE_PAGE_PATTERNS =
      patterns(
          "\\.sessions-page\\b",
          "\\.session-detail-page\\b",
          "\\.sd-shell\\b",
          "\\.sd-page\\b",
          "\\.dashboard-page\\b",
          "\\.projects-page\\b",
          "\\.agents-page\\b",
          "\\.glossary-page\\b");
  private static final List<Pattern> DEPENDENCY_PAGE_PATTERNS =
      patterns(
          "\\.sessions-page\\b",
          "\\.session-detail-page\\b",
          "\\.dashboard-page\\b",
          "\\.projects-page\\b",
          "\\.agents-page\\b",
          "\\.glossary-page\\b",
          "\\.state-panel\\b");
  private static final List<Pattern> SHELL_WRAPPERS =
      patterns("\\.sd-shell\\b", "\\.sd-page\\b", "\\.sd-content\\b");
  private static final Pattern CSS_COMMENT = Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL);
  private static final Pattern HEX_COLOR = Pattern.compile("(?<![a-zA-Z])#[0-9a-fA-F]{3,8}\\b");
  private static final Pattern BASE_ELEMENT =
      Pattern.compile(
          "^(html|body|div|span|p|a|img|ul|ol|li|table|th|td|thead|tbody|tfoot|"
              + "tr|h[1-6]|pre|code|blockquote|hr|input|button|textarea|select|form|"
              + "label|fieldset|legend|optgroup|option|datalist|output|progress|meter|"
              + "details|summary|dialog|main|header|footer|nav|article|section|aside|"
              + "figure|figcaption|canvas|svg|video|audio|source|track|embed|iframe|"
              + "object|param|map|area|link|meta|style|script|noscript|template|"
              + "slot|br|wbr|del|ins|s|u|b|i|em|strong|small|sub|sup|mark|abbr|"
              + "cite|dfn|data|time|kbd|var|samp|q|bdi|bdo|ruby|rt|rp)\\b");

  @Override
  public String id() {
    return ID;
  }

  @Override
  public boolean supportsPath(String relativePath) {
    if (!relativePath.startsWith(CSS_ROOT + "/") || !relativePath.endsWith(".css")) {
      return false;
    }
    return !relativePath.substring(CSS_ROOT.length() + 1).contains("/");
  }

  @Override
  public boolean usesChangedFiles() {
    return false;
  }

  @Override
  public List<Path> requiredInputs(Path repoRoot) {
    return List.of(repoRoot.resolve(CSS_ROOT));
  }

  @Override
  public Evaluation evaluate(QualityContext context) throws IOException {
    var result = inspect(context);
    writeArtifacts(context.qualityArtifactDir().resolve(ID), result);
    return new Evaluation(toViolations(result.blocks()), toAdvisories(result.advisories()));
  }

  private static OwnershipResult inspect(QualityContext context) throws IOException {
    var cssDirectory = context.repoRoot().resolve(CSS_ROOT);
    if (!Files.exists(cssDirectory)) {
      return new OwnershipResult(
          0,
          0,
          List.of(new Finding("missing-dir", "N/A", null, "CSS 目录不存在:" + cssDirectory)),
          List.of());
    }

    // Python Path.glob 在普通文件根上返回空集合；Java DirectoryStream 会抛 NotDirectoryException。
    var cssPaths =
        Files.isDirectory(cssDirectory) ? topLevelCssPaths(cssDirectory) : List.<Path>of();

    // 旧实现构造后从未使用 ui-primitives selector 集合；只保留可观察的严格 UTF-8 预读行为。
    var primitiveSource =
        cssPaths.stream()
            .filter(path -> path.getFileName().toString().equals("ui-primitives.css"))
            .findFirst();
    if (primitiveSource.isPresent()) {
      readStrictUtf8(primitiveSource.orElseThrow());
    }

    var blocks = new ArrayList<Finding>();
    var advisories = new ArrayList<Finding>();
    var selectorCount = 0;
    for (var path : cssPaths) {
      var fileName = path.getFileName().toString();
      var rules = extractRules(readStrictUtf8(path));
      selectorCount += rules.size();
      checkLayerPurity(fileName, rules, blocks);
      checkCrossLayerDuplicate(fileName, rules, advisories);
      checkDependencyDirection(fileName, rules, advisories);
      checkHardcodedColors(fileName, rules, advisories);
    }
    return new OwnershipResult(
        cssPaths.size(), selectorCount, List.copyOf(blocks), List.copyOf(advisories));
  }

  private static List<Path> topLevelCssPaths(Path cssDirectory) throws IOException {
    var paths = new ArrayList<Path>();
    // DirectoryStream 与旧 glob 一样保留顶层符号链接；坏链或目录目标会在严格读取时 fail closed。
    try (var entries = Files.newDirectoryStream(cssDirectory, "*.css")) {
      entries.forEach(paths::add);
    }
    paths.sort(CssOwnershipRule::compareByUnicodeCodePoint);
    return List.copyOf(paths);
  }

  private static int compareByUnicodeCodePoint(Path leftPath, Path rightPath) {
    var left = leftPath.toString();
    var right = rightPath.toString();
    var leftIndex = 0;
    var rightIndex = 0;
    while (leftIndex < left.length() && rightIndex < right.length()) {
      var leftCodePoint = left.codePointAt(leftIndex);
      var rightCodePoint = right.codePointAt(rightIndex);
      if (leftCodePoint != rightCodePoint) {
        return Integer.compare(leftCodePoint, rightCodePoint);
      }
      leftIndex += Character.charCount(leftCodePoint);
      rightIndex += Character.charCount(rightCodePoint);
    }
    return Integer.compare(left.length() - leftIndex, right.length() - rightIndex);
  }

  private static String readStrictUtf8(Path path) throws IOException {
    var text = Files.readString(path, StandardCharsets.UTF_8);
    // Python Path.read_text 使用 universal-newline 模式：CRLF 与单独 CR 都会在 parser 前变为 LF。
    return text.replace("\r\n", "\n").replace('\r', '\n');
  }

  private static List<CssRule> extractRules(String text) {
    var rules = new ArrayList<CssRule>();
    var stripped = CSS_COMMENT.matcher(text).replaceAll("");
    var codePoints = stripped.codePoints().toArray();
    var stack = new ArrayDeque<OpenRule>();
    for (int index = 0; index < codePoints.length; index++) {
      if (codePoints[index] == '{') {
        var selectorStart = index;
        while (selectorStart > 0 && "{};".indexOf(codePoints[selectorStart - 1]) < 0) {
          selectorStart--;
        }
        var selector = strip(new String(codePoints, selectorStart, index - selectorStart));
        stack.push(new OpenRule(selector, selectorStart));
      } else if (codePoints[index] == '}' && !stack.isEmpty()) {
        var opened = stack.pop();
        var body = strip(new String(codePoints, opened.start() + 1, index - opened.start() - 1));
        var line = originalLineAt(text, opened.start());
        if (line > 0) {
          rules.add(new CssRule(line, opened.selector(), body));
        }
      }
    }
    return List.copyOf(rules);
  }

  private static int originalLineAt(String text, int codePointOffset) {
    var position = 0;
    var lines = PythonTextSemantics.splitLines(text);
    for (int index = 0; index < lines.size(); index++) {
      var mappedLength = lines.get(index).codePointCount(0, lines.get(index).length()) + 1;
      if (codePointOffset >= position && codePointOffset < position + mappedLength) {
        return index + 1;
      }
      position += mappedLength;
    }
    return 0;
  }

  private static List<String> splitSelectors(String selectorText) {
    var depth = 0;
    var result = new ArrayList<String>();
    var current = new StringBuilder();
    for (int index = 0; index < selectorText.length(); index++) {
      var character = selectorText.charAt(index);
      if (character == '(') {
        depth++;
      } else if (character == ')') {
        depth--;
      }
      if (character == ',' && depth == 0) {
        addSelector(result, current);
        current.setLength(0);
      } else {
        current.append(character);
      }
    }
    if (!current.isEmpty()) {
      addSelector(result, current);
    }
    return List.copyOf(result);
  }

  private static void addSelector(List<String> result, StringBuilder raw) {
    var selector = strip(raw.toString());
    if (!selector.isEmpty() && !selector.startsWith("@")) {
      result.add(selector);
    }
  }

  private static void checkLayerPurity(String fileName, List<CssRule> rules, List<Finding> blocks) {
    switch (fileName) {
      case "tokens.css" -> checkTokenLayer(rules, blocks);
      case "base.css" -> checkBaseLayer(rules, blocks);
      case "shell.css" -> checkPageSelectors(fileName, rules, PAGE_PATTERNS, blocks);
      case "ui-primitives.css" ->
          checkPageSelectors(fileName, rules, PRIMITIVE_PAGE_PATTERNS, blocks);
      default -> {
        // 页面 CSS 没有低层纯度约束。
      }
    }
  }

  private static void checkTokenLayer(List<CssRule> rules, List<Finding> blocks) {
    for (var rule : rules) {
      if (!rule.selector().startsWith("@") && !rule.selector().equals(":root")) {
        blocks.add(
            new Finding(
                "layer-purity",
                "tokens.css",
                rule.line(),
                "tokens.css 不得包含选择器规则:'" + truncate(rule.selector(), 100) + "'"));
      }
    }
  }

  private static void checkBaseLayer(List<CssRule> rules, List<Finding> blocks) {
    for (var rule : rules) {
      if (rule.selector().startsWith("@")) {
        continue;
      }
      for (var selector : splitSelectors(rule.selector())) {
        if (selector.equals(":root")
            || selector.startsWith(":root")
            || BASE_ELEMENT.matcher(selector).find()
            || (selector.startsWith(":") && !selector.contains(".") && !selector.contains("#"))
            || selector.startsWith("*")
            || selector.startsWith("body")
            || selector.startsWith("html")) {
          continue;
        }
        blocks.add(
            new Finding(
                "layer-purity",
                "base.css",
                rule.line(),
                "base.css 包含非元素选择器:'" + truncate(selector, 100) + "'"));
      }
    }
  }

  private static void checkPageSelectors(
      String fileName, List<CssRule> rules, List<Pattern> forbiddenPatterns, List<Finding> blocks) {
    for (var rule : rules) {
      if (rule.selector().startsWith("@")) {
        continue;
      }
      for (var selector : splitSelectors(rule.selector())) {
        if (matchesAny(forbiddenPatterns, selector)) {
          var owner = fileName.equals("shell.css") ? "shell.css" : "ui-primitives.css";
          blocks.add(
              new Finding(
                  "layer-purity",
                  fileName,
                  rule.line(),
                  owner + " 包含页面级选择器:'" + truncate(selector, 100) + "'"));
        }
      }
    }
  }

  private static void checkCrossLayerDuplicate(
      String fileName, List<CssRule> rules, List<Finding> advisories) {
    if (LOW_LEVEL_FILES.contains(fileName)) {
      return;
    }
    for (var rule : rules) {
      if (rule.selector().startsWith("@")) {
        continue;
      }
      for (var selector : splitSelectors(rule.selector())) {
        if (GLOBAL_COMPONENTS.contains(selector)) {
          advisories.add(
              new Finding(
                  "cross-layer-duplicate",
                  fileName,
                  rule.line(),
                  fileName
                      + " 直接重写全局组件 '"
                      + selector
                      + "'(已在 ui-primitives.css 定义),应使用后代选择器或页面特有变体"));
        }
      }
    }
  }

  private static void checkDependencyDirection(
      String fileName, List<CssRule> rules, List<Finding> advisories) {
    if (!LOW_LEVEL_FILES.contains(fileName)) {
      return;
    }
    for (var rule : rules) {
      if (rule.selector().startsWith("@")) {
        continue;
      }
      if (fileName.equals("shell.css") && matchesAny(SHELL_WRAPPERS, rule.selector())) {
        continue;
      }
      if (matchesAny(DEPENDENCY_PAGE_PATTERNS, rule.selector())) {
        advisories.add(
            new Finding(
                "dependency-direction",
                fileName,
                rule.line(),
                fileName
                    + " 反向引用页面级选择器:'"
                    + truncate(rule.selector(), 100)
                    + "' (依赖方向应为 page -> ui-primitives -> shell -> base -> tokens)"));
      }
    }
  }

  private static void checkHardcodedColors(
      String fileName, List<CssRule> rules, List<Finding> advisories) {
    if (LOW_LEVEL_FILES.contains(fileName)) {
      return;
    }
    for (var rule : rules) {
      var colors = HEX_COLOR.matcher(rule.body());
      while (colors.find()) {
        var color = colors.group();
        if (SAFE_COLORS.contains(color.toLowerCase(Locale.ROOT))) {
          continue;
        }
        advisories.add(
            new Finding(
                "hardcoded-color",
                fileName,
                rule.line(),
                fileName
                    + " 使用硬编码颜色 '"
                    + color
                    + "'(选择器: '"
                    + truncate(rule.selector(), 60)
                    + "...'),建议使用 token 变量"));
      }
    }
  }

  private static List<QualityViolation> toViolations(List<Finding> findings) {
    return findings.stream()
        .map(
            finding ->
                new QualityViolation(
                    ID,
                    finding.relativePath(),
                    finding.line() == null ? 1 : finding.line(),
                    finding.rule().equals("missing-dir")
                        ? "CSS_DIRECTORY_MISSING"
                        : "CSS_LAYER_PURITY",
                    finding.detail(),
                    Map.of("artifactRule", finding.rule(), "file", finding.file())))
        .toList();
  }

  private static List<QualityAdvisory> toAdvisories(List<Finding> findings) {
    return findings.stream()
        .map(
            finding ->
                new QualityAdvisory(
                    ID,
                    finding.relativePath(),
                    finding.line(),
                    switch (finding.rule()) {
                      case "cross-layer-duplicate" -> "CSS_CROSS_LAYER_DUPLICATE";
                      case "dependency-direction" -> "CSS_DEPENDENCY_DIRECTION";
                      default -> "CSS_HARDCODED_COLOR";
                    },
                    finding.detail(),
                    Map.of("artifactRule", finding.rule(), "file", finding.file())))
        .toList();
  }

  private static void writeArtifacts(Path outputDirectory, OwnershipResult result)
      throws IOException {
    ArtifactPairPublisher.publish(
        outputDirectory,
        "css-ownership-report.txt",
        formatTextReport(result) + "\n",
        "css-ownership-gate.json",
        formatJsonReport(result));
  }

  private static String formatTextReport(OwnershipResult result) {
    var lines = new ArrayList<String>();
    lines.add("=".repeat(60));
    lines.add("CSS Ownership Gate Report");
    lines.add("=".repeat(60));
    lines.add("Files scanned:      " + result.filesScanned());
    lines.add("Selectors analyzed: " + result.selectorsAnalyzed());
    lines.add("Block violations:   " + result.blocks().size());
    lines.add("Warnings:           " + result.advisories().size());
    lines.add("");
    if (!result.blocks().isEmpty()) {
      lines.add("--- BLOCK violations ---");
      result.blocks().forEach(finding -> lines.add(formatFinding("  [BLOCK] ", finding)));
      lines.add("");
    }
    if (!result.advisories().isEmpty()) {
      lines.add("--- Warnings ---");
      result.advisories().forEach(finding -> lines.add(formatFinding("  [WARN]  ", finding)));
      lines.add("");
    }
    if (result.blocks().isEmpty() && result.advisories().isEmpty()) {
      lines.add("CSS ownership: PASS (no violations)");
    } else if (result.blocks().isEmpty()) {
      lines.add("CSS ownership: PASS (" + result.advisories().size() + " warnings)");
    } else {
      lines.add(
          "CSS ownership: FAIL ("
              + result.blocks().size()
              + " block, "
              + result.advisories().size()
              + " warn)");
    }
    lines.add("=".repeat(60));
    return String.join("\n", lines);
  }

  private static String formatFinding(String prefix, Finding finding) {
    var line = finding.line() == null ? "" : " (L" + finding.line() + ")";
    return prefix + finding.rule() + line + ": " + finding.file() + " — " + finding.detail();
  }

  private static String formatJsonReport(OwnershipResult result) {
    var output = new StringBuilder();
    output.append("{\n");
    output.append("  \"schemaVersion\": 1,\n");
    output.append("  \"gate\": \"css-ownership\",\n");
    output.append("  \"status\": \"").append(result.blocks().isEmpty() ? "PASS" : "FAIL");
    output.append("\",\n");
    output.append("  \"filesScanned\": ").append(result.filesScanned()).append(",\n");
    output.append("  \"selectorsAnalyzed\": ").append(result.selectorsAnalyzed()).append(",\n");
    output.append("  \"blockCount\": ").append(result.blocks().size()).append(",\n");
    output.append("  \"warningCount\": ").append(result.advisories().size()).append(",\n");
    appendFindingArray(output, "blocks", result.blocks());
    output.append(",\n");
    appendFindingArray(output, "warnings", result.advisories());
    return output.append("\n}\n").toString();
  }

  private static void appendFindingArray(
      StringBuilder output, String fieldName, List<Finding> findings) {
    output.append("  ").append(jsonString(fieldName)).append(": [");
    if (!findings.isEmpty()) {
      output.append('\n');
    }
    for (int index = 0; index < findings.size(); index++) {
      if (index > 0) {
        output.append(",\n");
      }
      var finding = findings.get(index);
      output.append("    {\n");
      output.append("      \"rule\": ").append(jsonString(finding.rule())).append(",\n");
      output.append("      \"file\": ").append(jsonString(finding.file())).append(",\n");
      output.append("      \"line\": ");
      output.append(finding.line() == null ? "null" : finding.line()).append(",\n");
      output.append("      \"detail\": ").append(jsonString(finding.detail())).append('\n');
      output.append("    }");
    }
    if (!findings.isEmpty()) {
      output.append('\n').append("  ");
    }
    output.append(']');
  }

  private static String jsonString(String value) {
    var output = new StringBuilder("\"");
    for (int index = 0; index < value.length(); index++) {
      var character = value.charAt(index);
      switch (character) {
        case '"' -> output.append("\\\"");
        case '\\' -> output.append("\\\\");
        case '\b' -> output.append("\\b");
        case '\f' -> output.append("\\f");
        case '\n' -> output.append("\\n");
        case '\r' -> output.append("\\r");
        case '\t' -> output.append("\\t");
        default -> {
          if (character < 0x20) {
            output.append(String.format(Locale.ROOT, "\\u%04x", (int) character));
          } else {
            output.append(character);
          }
        }
      }
    }
    return output.append('"').toString();
  }

  private static String strip(String value) {
    return PythonTextSemantics.strip(value);
  }

  private static String truncate(String value, int maximumCodePoints) {
    if (value.codePointCount(0, value.length()) <= maximumCodePoints) {
      return value;
    }
    return value.substring(0, value.offsetByCodePoints(0, maximumCodePoints));
  }

  private static boolean matchesAny(List<Pattern> patterns, String value) {
    return patterns.stream().anyMatch(pattern -> pattern.matcher(value).find());
  }

  private static List<Pattern> patterns(String... expressions) {
    return java.util.Arrays.stream(expressions).map(Pattern::compile).toList();
  }

  /**
   * parser 返回的一条 CSS rule。
   *
   * @param line 历史偏移算法得到的源码行号。
   * @param selector 原始 selector 文本。
   * @param body 旧 parser 定义的 rule body 文本。
   */
  private record CssRule(int line, String selector, String body) {}

  /**
   * 尚未闭合的 CSS 块。
   *
   * @param selector 块头 selector。
   * @param start selector 在去注释文本中的 code-point 偏移。
   */
  private record OpenRule(String selector, int start) {}

  /**
   * artifact 使用的原始诊断。
   *
   * @param rule artifact 规则名。
   * @param file CSS 文件名。
   * @param line 源码行号；目录缺失时为 null。
   * @param detail 与旧 owner 一致的中文说明。
   */
  private record Finding(String rule, String file, Integer line, String detail) {
    private String relativePath() {
      return file.equals("N/A") ? CSS_ROOT : CSS_ROOT + "/" + file;
    }
  }

  /**
   * 单次 CSS ownership 扫描结果。
   *
   * @param filesScanned 顶层 CSS 文件数。
   * @param selectorsAnalyzed parser 返回的 rule tuple 数。
   * @param blocks 阻断项。
   * @param advisories 非阻断建议项。
   */
  private record OwnershipResult(
      int filesScanned, int selectorsAnalyzed, List<Finding> blocks, List<Finding> advisories) {}
}
