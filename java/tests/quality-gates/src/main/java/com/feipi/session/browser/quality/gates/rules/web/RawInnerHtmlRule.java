package com.feipi.session.browser.quality.gates.rules.web;

import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule;
import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule.BaselineUpdate;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.core.RepositorySourceSet.SourceText;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 阻断 static/js、tests 与 scripts 中新增的逐行 raw innerHTML 赋值。 */
public final class RawInnerHtmlRule implements BaselineUpdatableRule {

  private static final String ID = "raw-innerhtml";
  private static final String STATIC_JS_ROOT = "java/web/src/main/resources/static/js";
  private static final String TESTS_ROOT = "tests";
  private static final String SCRIPTS_ROOT = "scripts";
  private static final String BASELINE = "config/web-quality-baselines.json";
  private static final String SPACE = PythonTextSemantics.WHITESPACE_CLASS;
  private static final Pattern ASSIGNMENT = Pattern.compile("\\.innerHTML" + SPACE + "*=");
  private static final Pattern COMMENT_LINE = Pattern.compile("^" + SPACE + "*(?://|/\\*|\\*)");
  private static final Pattern CLEAR_ASSIGNMENT =
      Pattern.compile("\\.innerHTML" + SPACE + "*=" + SPACE + "*['\"]" + SPACE + "*['\"]");

  @Override
  public String id() {
    return ID;
  }

  @Override
  public boolean supportsPath(String relativePath) {
    return isSupportedPath(relativePath);
  }

  @Override
  public boolean usesChangedFiles() {
    return false;
  }

  @Override
  public List<Path> requiredInputs(Path repoRoot) {
    return List.of(repoRoot.resolve(BASELINE));
  }

  @Override
  public List<QualityViolation> check(QualityContext context) {
    var known =
        new LinkedHashSet<>(
            WebQualityBaseline.load(context.repoRoot().resolve(BASELINE)).entries(ID, "entries"));
    var violations = new ArrayList<QualityViolation>();
    for (var finding : findings(context)) {
      if (!known.contains(finding.key())) {
        violations.add(
            new QualityViolation(
                ID,
                finding.path(),
                finding.line(),
                "RAW_INNERHTML_NEW",
                "检测到新增 innerHTML 赋值，违反 raw-innerHTML 阻断策略。"
                    + "请先改用 textContent 或 escapeHtml()；只有经审阅后才可显式更新 baseline。",
                Map.of(
                    "isClear", Boolean.toString(finding.clear()), "snippet", finding.snippet())));
      }
    }
    return List.copyOf(violations);
  }

  @Override
  public BaselineUpdate baselineUpdate(QualityContext context) {
    var entries = new LinkedHashSet<String>();
    findings(context).forEach(finding -> entries.add(finding.key()));
    return new BaselineUpdate(
        context.repoRoot().resolve(BASELINE), Map.of("entries", List.copyOf(entries)));
  }

  private static List<Finding> findings(QualityContext context) {
    var sources =
        context.repositorySources().sources().stream()
            .filter(source -> isSupportedPath(source.relativePath()))
            .sorted(
                Comparator.comparingInt((SourceText source) -> sourceOrder(source.relativePath()))
                    .thenComparing(SourceText::relativePath))
            .toList();
    var findings = new ArrayList<Finding>();
    for (var source : sources) {
      var lines = PythonTextSemantics.splitLines(source.text());
      for (int index = 0; index < lines.size(); index++) {
        var line = lines.get(index);
        var stripped = PythonTextSemantics.strip(line);
        if (COMMENT_LINE.matcher(stripped).find() || !ASSIGNMENT.matcher(line).find()) {
          continue;
        }
        findings.add(
            new Finding(
                source.relativePath(),
                index + 1,
                CLEAR_ASSIGNMENT.matcher(line).find(),
                truncate(stripped, 120)));
      }
    }
    return List.copyOf(findings);
  }

  private static boolean isBelow(String relativePath, String root) {
    return relativePath.startsWith(root + "/");
  }

  private static boolean isSupportedPath(String relativePath) {
    return relativePath.endsWith(".js")
        && (isBelow(relativePath, STATIC_JS_ROOT)
            || isBelow(relativePath, TESTS_ROOT)
            || isBelow(relativePath, SCRIPTS_ROOT));
  }

  private static int sourceOrder(String relativePath) {
    if (isBelow(relativePath, STATIC_JS_ROOT)) {
      return 0;
    }
    if (isBelow(relativePath, TESTS_ROOT)) {
      return 1;
    }
    return 2;
  }

  private static String truncate(String value, int maximumCodePoints) {
    var codePoints = value.codePointCount(0, value.length());
    if (codePoints <= maximumCodePoints) {
      return value;
    }
    return value.substring(0, value.offsetByCodePoints(0, maximumCodePoints));
  }

  /**
   * 单行 innerHTML 赋值及其诊断元数据。
   *
   * @param path 仓库相对路径
   * @param line 行号
   * @param clear 是否为清空赋值
   * @param snippet 诊断片段
   */
  private record Finding(String path, int line, boolean clear, String snippet) {
    private String key() {
      return path + ":" + line;
    }
  }
}
