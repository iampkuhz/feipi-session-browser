package com.feipi.session.browser.quality.gates.rules;

import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** 检查固定 Jinja 模板目录的基础闭合语法与 inline onclick 禁令。 */
public final class TemplateContractRule implements QualityRule {

  private static final String TEMPLATES_ROOT = "java/web/src/main/resources/templates";

  @Override
  public String id() {
    return "template-contract";
  }

  @Override
  public boolean supportsPath(String relativePath) {
    return relativePath.startsWith(TEMPLATES_ROOT + "/") && relativePath.endsWith(".html");
  }

  @Override
  public boolean usesChangedFiles() {
    return false;
  }

  @Override
  public List<Path> requiredInputs(Path repoRoot) {
    return List.of(repoRoot.resolve(TEMPLATES_ROOT));
  }

  @Override
  public List<QualityViolation> check(QualityContext context) {
    var templatesRoot = context.repoRoot().resolve(TEMPLATES_ROOT);
    if (!Files.exists(templatesRoot)) {
      return List.of(
          violation(TEMPLATES_ROOT, 1, "TEMPLATE_DIRECTORY_MISSING", "模板目录不存在:" + templatesRoot));
    }
    var templates =
        context.repositorySources().sources().stream()
            .filter(source -> supportsPath(source.relativePath()))
            .toList();
    if (templates.isEmpty()) {
      return List.of(
          violation(TEMPLATES_ROOT, 1, "TEMPLATE_HTML_MISSING", "模板目录没有 html 文件:" + templatesRoot));
    }

    var violations = new ArrayList<QualityViolation>();
    for (var template : templates) {
      var text = template.text();
      if (text.contains("{%") && !text.contains("%}")) {
        violations.add(
            violation(
                template.relativePath(),
                lineOf(text, "{%"),
                "JINJA_BLOCK_UNCLOSED",
                "Jinja block 可能未闭合."));
      }
      if (text.contains("{{") && !text.contains("}}")) {
        violations.add(
            violation(
                template.relativePath(),
                lineOf(text, "{{"),
                "JINJA_EXPRESSION_UNCLOSED",
                "Jinja expression 可能未闭合."));
      }
      if (text.contains("onclick=")) {
        violations.add(
            violation(
                template.relativePath(),
                lineOf(text, "onclick="),
                "ONCLICK_FORBIDDEN",
                "禁止 inline onclick,改用 static JS 绑定."));
      }
    }
    return List.copyOf(violations);
  }

  private static int lineOf(String text, String token) {
    var index = text.indexOf(token);
    var line = 1;
    for (int offset = 0; offset < index; offset++) {
      if (text.charAt(offset) == '\n') {
        line++;
      }
    }
    return line;
  }

  private static QualityViolation violation(String path, int line, String code, String message) {
    return new QualityViolation("template-contract", path, line, code, message, Map.of());
  }
}
