package com.feipi.session.browser.quality.gates.rules.web;

import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule;
import com.feipi.session.browser.quality.gates.core.BaselineUpdatableRule.BaselineUpdate;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.core.RepositorySourceSet.SourceText;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 阻断 templates HTML 与 static/js 中新增的布局 inline style。 */
public final class LayoutInlineStyleRule implements BaselineUpdatableRule {

  private static final String ID = "layout-inline-style";
  private static final String TEMPLATES_ROOT = "java/web/src/main/resources/templates";
  private static final String STATIC_JS_ROOT = "java/web/src/main/resources/static/js";
  private static final String BASELINE =
      "java/tests/quality-gates/config/web-quality-baselines.json";
  private static final String SPACE = PythonTextSemantics.WHITESPACE_CLASS;
  private static final Pattern STYLE_ATTRIBUTE =
      Pattern.compile(
          "style" + SPACE + "*=" + SPACE + "*['\"]([^'\"]*)['\"]",
          Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS);
  private static final Pattern PURE_TEMPLATE_VALUE =
      Pattern.compile("^" + SPACE + "*\\{\\{.*\\}\\}" + SPACE + "*$");
  private static final Pattern CUSTOM_PROPERTY =
      Pattern.compile("--[\\w-]+" + SPACE + "*:", Pattern.UNICODE_CHARACTER_CLASS);
  private static final Pattern SEPARATORS = Pattern.compile("(?:;|" + SPACE + ")+");
  private static final Pattern LAYOUT_PROPERTY =
      Pattern.compile(
          "\\b(display|position|flex|grid|width|height|min-width|min-height|max-width|max-height"
              + "|top|left|right|bottom"
              + "|padding|padding-top|padding-right|padding-bottom|padding-left"
              + "|margin|margin-top|margin-right|margin-bottom|margin-left"
              + "|overflow|overflow-x|overflow-y|z-index)"
              + SPACE
              + "*:",
          Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS);
  private static final Pattern JS_STYLE_ASSIGNMENT =
      Pattern.compile(
          "\\.style\\.(display|position|flex|grid|width|height|minWidth|minHeight|maxWidth|maxHeight"
              + "|top|left|right|bottom|padding|paddingTop|paddingRight|paddingBottom|paddingLeft"
              + "|margin|marginTop|marginRight|marginBottom|marginLeft"
              + "|overflow|overflowX|overflowY|zIndex)"
              + SPACE
              + "*=");
  private static final Pattern JS_COMMENT_LINE = Pattern.compile("^" + SPACE + "*(?://|/\\*|\\*)");

  @Override
  public String id() {
    return ID;
  }

  @Override
  public boolean supportsPath(String relativePath) {
    return (isBelow(relativePath, TEMPLATES_ROOT) && relativePath.endsWith(".html"))
        || (isBelow(relativePath, STATIC_JS_ROOT) && relativePath.endsWith(".js"));
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
                "LAYOUT_INLINE_STYLE_NEW",
                "检测到新增 layout inline style，违反 layout-inline-style 阻断策略。"
                    + "请移除 inline style 并改用 CSS class 或 CSS custom property。",
                Map.of("snippet", finding.snippet(), "source", finding.source())));
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
    var htmlSources = sources(context, TEMPLATES_ROOT, ".html");
    var jsSources = sources(context, STATIC_JS_ROOT, ".js");
    var findings = new ArrayList<Finding>();
    scanHtml(htmlSources, findings);
    scanJavaScript(jsSources, findings);
    return List.copyOf(findings);
  }

  private static List<SourceText> sources(QualityContext context, String root, String suffix) {
    return context.repositorySources().sources().stream()
        .filter(source -> isBelow(source.relativePath(), root))
        .filter(source -> source.relativePath().endsWith(suffix))
        .toList();
  }

  private static void scanHtml(List<SourceText> sources, List<Finding> findings) {
    for (var source : sources) {
      var lines = PythonTextSemantics.splitLines(source.text());
      for (int index = 0; index < lines.size(); index++) {
        var line = lines.get(index);
        var stripped = PythonTextSemantics.strip(line);
        if (stripped.startsWith("{#") || stripped.startsWith("<!--")) {
          continue;
        }
        var attributes = STYLE_ATTRIBUTE.matcher(line);
        while (attributes.find()) {
          var value = attributes.group(1);
          if (PURE_TEMPLATE_VALUE.matcher(value).matches() || customPropertyOnly(value)) {
            continue;
          }
          if (LAYOUT_PROPERTY.matcher(value).find()) {
            findings.add(
                new Finding(source.relativePath(), index + 1, "html", truncate(stripped, 140)));
          }
        }
      }
    }
  }

  private static boolean customPropertyOnly(String value) {
    if (!CUSTOM_PROPERTY.matcher(value).find()) {
      return false;
    }
    var nonCustom = PythonTextSemantics.strip(CUSTOM_PROPERTY.matcher(value).replaceAll(""));
    nonCustom = PythonTextSemantics.strip(SEPARATORS.matcher(nonCustom).replaceAll(" "));
    return nonCustom.isEmpty() || !LAYOUT_PROPERTY.matcher(nonCustom).find();
  }

  private static void scanJavaScript(List<SourceText> sources, List<Finding> findings) {
    for (var source : sources) {
      var lines = PythonTextSemantics.splitLines(source.text());
      for (int index = 0; index < lines.size(); index++) {
        var line = lines.get(index);
        var stripped = PythonTextSemantics.strip(line);
        if (!JS_COMMENT_LINE.matcher(stripped).find() && JS_STYLE_ASSIGNMENT.matcher(line).find()) {
          findings.add(
              new Finding(source.relativePath(), index + 1, "js", truncate(stripped, 140)));
        }
      }
    }
  }

  private static boolean isBelow(String relativePath, String root) {
    return relativePath.startsWith(root + "/");
  }

  private static String truncate(String value, int maximumCodePoints) {
    var codePoints = value.codePointCount(0, value.length());
    if (codePoints <= maximumCodePoints) {
      return value;
    }
    return value.substring(0, value.offsetByCodePoints(0, maximumCodePoints));
  }

  /**
   * 单行 layout inline style 及其 HTML/JS 来源。
   *
   * @param path 仓库相对路径
   * @param line 行号
   * @param source 来源类型
   * @param snippet 诊断片段
   */
  private record Finding(String path, int line, String source, String snippet) {
    private String key() {
      return path + ":" + line;
    }
  }
}
