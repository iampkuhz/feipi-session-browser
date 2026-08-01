package com.feipi.session.browser.quality.gates.rules.web;

import com.feipi.session.browser.quality.gates.core.JavaSourceSet;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.core.RepositorySourceSet.SourceText;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 检查 Java Web 静态资源独有的加载、安全和组件边界契约。 */
public final class StaticResourceContractRule implements QualityRule {

  private static final String ID = "static-resource-contract";
  private static final String STATIC_ROOT = "java/web/src/main/resources/static";
  private static final String TEMPLATES_ROOT = "java/web/src/main/resources/templates";
  private static final String BASE_TEMPLATE = TEMPLATES_ROOT + "/base.html";
  private static final String BASELINE = "config/web-quality-baselines.json";
  private static final String COMPONENT_BASELINE = "component_override_violations";
  private static final String SELECTOR_BASELINE = "selector_depth_violations";
  private static final int SELECTOR_BLOCK_DEPTH = 3;

  private static final Pattern CSS_COMMENT = Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL);
  private static final Pattern DUPLICATE_CSS = Pattern.compile("href=\"([^\"]*\\.css[^\"]*)\"");
  private static final Pattern CSS_BLOCK =
      Pattern.compile("([^{;]+?)\\s*\\{([^}]*)}", Pattern.DOTALL);
  private static final Pattern PAYLOAD_MODAL =
      Pattern.compile(
          "^(?!\\s*/\\*|\\s*\\*|\\s*\\.session-detail-page|\\s*\\.sd-page|"
              + "\\s*\\.sd-shell|\\s*\\.sd-payload-modal)\\s*"
              + "(?:\\.payload-modal\\b(?![-_:\\s]*--)|#payload-modal\\b)",
          Pattern.MULTILINE);
  private static final Pattern SELECTOR_COMBINATOR = Pattern.compile("\\s*(?:>|[+~])\\s*|\\s+");
  private static final Pattern PARENTHESIZED = Pattern.compile("\\([^)]*\\)");

  private static final Set<String> BASE_CSS_NAMES =
      Set.of("tokens.css", "base.css", "shell.css", "ui-primitives.css");
  private static final Set<String> COMPONENT_EXEMPT_FILES =
      Set.of("ui-primitives.css", "tokens.css", "base.css", "shell.css");
  private static final List<String> EXPECTED_BASE_ITEMS =
      List.of(
          "/static/css/tokens.css",
          "/static/css/base.css",
          "/static/css/shell.css",
          "/static/css/ui-primitives.css",
          "{% block head_extra %}");
  private static final List<String> PRIMITIVE_ROOT_CLASSES =
      List.of(
          ".avatar",
          ".badge",
          ".btn",
          ".card",
          ".data-table",
          ".filter-card",
          ".filter-chip",
          ".icon-btn",
          ".icon-button",
          ".menu-popover",
          ".metric-card",
          ".metric-grid",
          ".modal",
          ".page-head",
          ".pagination",
          ".payload-modal",
          ".pill",
          ".popover",
          ".section",
          ".section-head",
          ".state-strip",
          ".tab-btn",
          ".tab-nav",
          ".tabs",
          ".toast",
          ".tooltip",
          ".ui-btn");

  @Override
  public String id() {
    return ID;
  }

  @Override
  public boolean supportsPath(String relativePath) {
    if (relativePath.startsWith(STATIC_ROOT + "/")) {
      return relativePath.endsWith(".css") || relativePath.endsWith(".js");
    }
    return relativePath.startsWith(TEMPLATES_ROOT + "/") && relativePath.endsWith(".html");
  }

  @Override
  public boolean usesChangedFiles() {
    return false;
  }

  @Override
  public List<Path> requiredInputs(Path repoRoot) {
    return List.of(
        repoRoot.resolve(STATIC_ROOT), repoRoot.resolve(BASE_TEMPLATE), repoRoot.resolve(BASELINE));
  }

  @Override
  public List<QualityViolation> check(QualityContext context) {
    var staticRoot = context.repoRoot().resolve(STATIC_ROOT);
    if (!Files.exists(staticRoot)) {
      return List.of(
          violation(
              STATIC_ROOT, 1, "STATIC_DIRECTORY_MISSING", "静态资源目录不存在:" + staticRoot, Map.of()));
    }

    var cssSources = sourcesWithSuffix(context, STATIC_ROOT, ".css");
    var jsSources = sourcesWithSuffix(context, STATIC_ROOT, ".js");
    var htmlSources = sourcesWithSuffix(context, TEMPLATES_ROOT, ".html");
    var violations = new ArrayList<QualityViolation>();

    checkNoImportant(cssSources, violations);
    checkCssLoadOrder(context, htmlSources, violations);
    checkNoDeadCss(cssSources, violations);
    checkNoDuplicateBaseCss(context, htmlSources, violations);
    checkPayloadModalOwnership(cssSources, violations);
    checkNoEval(jsSources, violations);

    var baseline = WebQualityBaseline.load(context.repoRoot().resolve(BASELINE));
    checkComponentOverrides(cssSources, baseline.entries(ID, COMPONENT_BASELINE), violations);
    checkSelectorDepth(cssSources, baseline.entries(ID, SELECTOR_BASELINE), violations);
    return List.copyOf(violations);
  }

  private static List<SourceText> sourcesWithSuffix(
      QualityContext context, String root, String suffix) {
    return context.repositorySources().sources().stream()
        .filter(source -> source.relativePath().startsWith(root + "/"))
        .filter(source -> source.relativePath().endsWith(suffix))
        .toList();
  }

  private static void checkNoImportant(
      List<SourceText> cssSources, List<QualityViolation> violations) {
    for (var source : cssSources) {
      var index = source.text().indexOf("!important");
      if (index >= 0) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(source.text(), index),
                "IMPORTANT_FORBIDDEN",
                "禁止 !important(contract: payload-modal-contract).",
                Map.of()));
      }
    }
  }

  private static void checkCssLoadOrder(
      QualityContext context, List<SourceText> htmlSources, List<QualityViolation> violations) {
    var basePath = context.repoRoot().resolve(BASE_TEMPLATE);
    if (!Files.exists(basePath)) {
      violations.add(
          violation(
              BASE_TEMPLATE,
              1,
              "BASE_TEMPLATE_MISSING",
              "css-load-order-contract: base.html 不存在:" + basePath,
              Map.of()));
      return;
    }
    var baseSource =
        htmlSources.stream()
            .filter(source -> BASE_TEMPLATE.equals(source.relativePath()))
            .findFirst()
            .orElse(null);
    if (baseSource == null) {
      violations.add(
          violation(
              BASE_TEMPLATE,
              1,
              "BASE_TEMPLATE_INPUT_MISSING",
              "css-load-order-contract: base.html 未包含在静态资源输入中.",
              Map.of()));
      return;
    }

    String baseText;
    try {
      // 旧 owner 只对 base.html 使用严格 UTF-8；其他 Web 资源继续采用 replacement 解码。
      baseText = Files.readString(basePath, StandardCharsets.UTF_8);
    } catch (IOException exception) {
      violations.add(
          violation(
              BASE_TEMPLATE,
              1,
              "BASE_TEMPLATE_UTF8_INVALID",
              "css-load-order-contract: base.html 无法按严格 UTF-8 读取.",
              Map.of()));
      return;
    }

    var positions = new ArrayList<Integer>();
    for (var item : EXPECTED_BASE_ITEMS) {
      var position = baseText.indexOf(item);
      if (position < 0) {
        violations.add(
            violation(
                BASE_TEMPLATE,
                1,
                "CSS_LOAD_ITEM_MISSING",
                "css-load-order-contract: 缺失必需项 '" + item + "'",
                Map.of("item", item)));
        return;
      }
      positions.add(position);
    }
    for (int index = 0; index < positions.size() - 1; index++) {
      if (positions.get(index) >= positions.get(index + 1)) {
        var before = EXPECTED_BASE_ITEMS.get(index);
        var after = EXPECTED_BASE_ITEMS.get(index + 1);
        violations.add(
            violation(
                BASE_TEMPLATE,
                lineAt(baseText, positions.get(index)),
                "CSS_LOAD_ORDER_INVALID",
                "css-load-order-contract: '"
                    + before
                    + "' 必须在 '"
                    + after
                    + "' 之前加载(位置 "
                    + positions.get(index)
                    + " vs "
                    + positions.get(index + 1)
                    + ").",
                Map.of("before", before, "after", after)));
      }
    }
  }

  private static void checkNoDeadCss(
      List<SourceText> cssSources, List<QualityViolation> violations) {
    for (var source : cssSources) {
      if (isImportWrapper(source.text())) {
        continue;
      }
      var stripped = stripCssComments(source.text()).strip();
      if (stripped.isEmpty()) {
        violations.add(
            violation(
                source.relativePath(), 1, "DEAD_CSS_EMPTY", "死 CSS 文件(只有注释或空白,无有效规则).", Map.of()));
      } else if (!stripped.contains("{") && !stripped.contains("}")) {
        violations.add(
            violation(
                source.relativePath(),
                1,
                "DEAD_CSS_NO_RULE_BODY",
                "死 CSS 文件(无 CSS rule body).",
                Map.of()));
      }
    }
  }

  private static boolean isImportWrapper(String text) {
    var stripped = stripCssComments(text).strip();
    if (stripped.isEmpty()) {
      return false;
    }
    var hasImport =
        stripped.lines().map(String::strip).anyMatch(line -> line.startsWith("@import"));
    var hasRules = stripped.contains("{") && stripped.contains("}");
    return hasImport && !hasRules;
  }

  private static void checkNoDuplicateBaseCss(
      QualityContext context, List<SourceText> htmlSources, List<QualityViolation> violations) {
    if (!Files.exists(context.repoRoot().resolve(TEMPLATES_ROOT))) {
      return;
    }
    for (var source : htmlSources) {
      if ("base.html".equals(source.path().getFileName().toString())) {
        continue;
      }
      var duplicates = new TreeSet<String>();
      var matcher = DUPLICATE_CSS.matcher(source.text());
      var firstIndex = -1;
      while (matcher.find()) {
        var link = matcher.group(1);
        var basename = link.substring(link.lastIndexOf('/') + 1);
        var query = basename.indexOf('?');
        if (query >= 0) {
          basename = basename.substring(0, query);
        }
        if (BASE_CSS_NAMES.contains(basename)) {
          duplicates.add(basename);
          if (firstIndex < 0) {
            firstIndex = matcher.start();
          }
        }
      }
      if (!duplicates.isEmpty()) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(source.text(), firstIndex),
                "DUPLICATE_BASE_CSS",
                "页面模板重复加载 base 已加载的 CSS: " + String.join(", ", duplicates) + ".",
                Map.of("stylesheets", String.join(",", duplicates))));
      }
    }
  }

  private static void checkPayloadModalOwnership(
      List<SourceText> cssSources, List<QualityViolation> violations) {
    for (var source : cssSources) {
      var fileName = source.path().getFileName().toString();
      if (Set.of("ui-primitives.css", "tokens.css", "base.css").contains(fileName)
          || isInUiPrimitivesDirectory(source.path())) {
        continue;
      }
      var matcher = PAYLOAD_MODAL.matcher(source.text());
      var count = 0;
      var firstIndex = -1;
      while (matcher.find()) {
        if (firstIndex < 0) {
          firstIndex = matcher.start();
        }
        count++;
      }
      if (count > 0) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(source.text(), firstIndex),
                "PAYLOAD_MODAL_OWNER",
                "禁止裸 payload-modal 定义(" + count + " 处),应收敛至 ui-primitives.css.",
                Map.of("count", Integer.toString(count))));
      }
    }
  }

  private static void checkNoEval(List<SourceText> jsSources, List<QualityViolation> violations) {
    for (var source : jsSources) {
      var index = source.text().indexOf("eval(");
      if (index >= 0) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(source.text(), index),
                "EVAL_FORBIDDEN",
                "禁止 eval.",
                Map.of()));
      }
    }
  }

  private static void checkComponentOverrides(
      List<SourceText> cssSources,
      List<String> baselineEntries,
      List<QualityViolation> violations) {
    for (var source : cssSources) {
      if (COMPONENT_EXEMPT_FILES.contains(source.path().getFileName().toString())
          || isInUiPrimitivesDirectory(source.path())) {
        continue;
      }
      var stripped = stripCssComments(source.text());
      var matcher = CSS_BLOCK.matcher(stripped);
      var found = new LinkedHashSet<String>();
      var firstIndex = -1;
      while (matcher.find()) {
        var selectors = matcher.group(1).strip();
        var body = matcher.group(2).strip();
        if (selectors.startsWith("@") || body.contains("{")) {
          continue;
        }
        for (var rawSelector : selectors.split(",")) {
          var selector = rawSelector.strip();
          if (selector.isEmpty()) {
            continue;
          }
          for (var component : PRIMITIVE_ROOT_CLASSES) {
            if (isBareComponent(selector, component) && found.add(component) && firstIndex < 0) {
              firstIndex = matcher.start();
            }
          }
        }
      }
      if (found.isEmpty()) {
        continue;
      }
      var legacy =
          legacyRelativePath(source)
              + ": 页面 CSS 裸定义原语根组件: "
              + String.join(", ", found)
              + ",应收敛至 ui-primitives.css 或使用后代/页面前缀选择器.";
      if (!isKnownDebt(legacy, baselineEntries)) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(stripped, firstIndex),
                "COMPONENT_OVERRIDE_NEW",
                "[component-override] 新增: " + legacy,
                Map.of("components", String.join(",", found))));
      }
    }
  }

  private static void checkSelectorDepth(
      List<SourceText> cssSources,
      List<String> baselineEntries,
      List<QualityViolation> violations) {
    for (var source : cssSources) {
      var stripped = stripCssComments(source.text());
      var matcher = CSS_BLOCK.matcher(stripped);
      var depthViolations = new ArrayList<String>();
      var firstIndex = -1;
      while (matcher.find()) {
        var selectors = matcher.group(1).strip();
        var body = matcher.group(2).strip();
        if (selectors.startsWith("@") || body.contains("{")) {
          continue;
        }
        for (var rawSelector : selectors.split(",")) {
          var selector = rawSelector.strip();
          if (selector.isEmpty() || selector.startsWith("@")) {
            continue;
          }
          var depth = selectorDepth(selector);
          if (depth > SELECTOR_BLOCK_DEPTH) {
            if (firstIndex < 0) {
              firstIndex = matcher.start();
            }
            depthViolations.add(selector + " (depth=" + depth + ")");
          }
        }
      }
      if (depthViolations.isEmpty()) {
        continue;
      }
      var preview = depthViolations.subList(0, Math.min(5, depthViolations.size()));
      var legacy =
          legacyRelativePath(source)
              + ": 选择器深度超过 "
              + SELECTOR_BLOCK_DEPTH
              + ": "
              + String.join("; ", preview);
      if (!isKnownDebt(legacy, baselineEntries)) {
        violations.add(
            violation(
                source.relativePath(),
                lineAt(stripped, firstIndex),
                "SELECTOR_DEPTH_NEW",
                "[selector-depth] 新增: " + legacy,
                Map.of("findingCount", Integer.toString(depthViolations.size()))));
      }
    }
  }

  private static int selectorDepth(String selector) {
    var matcher = PARENTHESIZED.matcher(selector);
    var protectedSelector = new StringBuffer();
    var index = 0;
    while (matcher.find()) {
      matcher.appendReplacement(
          protectedSelector, Matcher.quoteReplacement("__B" + index++ + "__"));
    }
    matcher.appendTail(protectedSelector);
    var depth = 0;
    for (var segment : SELECTOR_COMBINATOR.split(protectedSelector)) {
      if (!segment.strip().isEmpty()) {
        depth++;
      }
    }
    return depth;
  }

  private static boolean isBareComponent(String selector, String component) {
    if (!selector.startsWith(component)) {
      return false;
    }
    if (selector.length() == component.length()) {
      return true;
    }
    var next = selector.charAt(component.length());
    return Character.isWhitespace(next)
        || next == ':'
        || next == '.'
        || next == '#'
        || next == '['
        || next == ']'
        || next == '>'
        || next == '+'
        || next == '~';
  }

  private static boolean isKnownDebt(String result, List<String> baselineEntries) {
    var tokens = new LinkedHashSet<String>();
    for (var item : baselineEntries) {
      tokens.add(item);
      var colon = item.indexOf(':');
      if (colon >= 0) {
        tokens.add(item.substring(0, colon));
        var selector = item.substring(colon + 1).strip();
        var detail = selector.indexOf(" (");
        if (detail >= 0) {
          selector = selector.substring(0, detail).strip();
        }
        if (!selector.isEmpty()) {
          tokens.add(selector);
        }
      }
    }
    return tokens.stream().anyMatch(result::contains);
  }

  private static boolean isInUiPrimitivesDirectory(Path path) {
    var parent = path.getParent();
    return parent != null && parent.getFileName().toString().contains("ui-primitives");
  }

  private static String stripCssComments(String text) {
    return CSS_COMMENT.matcher(text).replaceAll("");
  }

  private static String legacyRelativePath(SourceText source) {
    var ancestor = source.path();
    for (int depth = 0; depth < 4 && ancestor != null; depth++) {
      ancestor = ancestor.getParent();
    }
    if (ancestor == null) {
      return source.relativePath();
    }
    return JavaSourceSet.normalize(ancestor.relativize(source.path()));
  }

  private static int lineAt(String text, int offset) {
    var line = 1;
    for (int index = 0; index < Math.max(0, offset); index++) {
      if (text.charAt(index) == '\n') {
        line++;
      }
    }
    return line;
  }

  private static QualityViolation violation(
      String path, int line, String code, String message, Map<String, String> attributes) {
    return new QualityViolation(ID, path, line, code, message, attributes);
  }
}
