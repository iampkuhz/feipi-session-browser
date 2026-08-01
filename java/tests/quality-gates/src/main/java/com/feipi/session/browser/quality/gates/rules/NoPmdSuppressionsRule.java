package com.feipi.session.browser.quality.gates.rules;

import com.feipi.session.browser.quality.gates.core.JavaSourceSet.ParsedSource;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.sun.source.tree.AnnotationTree;
import com.sun.source.util.TreePathScanner;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 禁止通过 {@code @SuppressWarnings("PMD.*")} 绕过自定义 PMD 规则。 */
public final class NoPmdSuppressionsRule implements QualityRule {

  private static final String ID = "no-pmd-suppressions";
  private static final Pattern PMD_RULE = Pattern.compile("[\\\"'](PMD\\.[^\\\"']+)[\\\"']");
  private static final String BACKGROUND_SCANNER =
      "java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/BackgroundScanner.java";

  @Override
  public String id() {
    return ID;
  }

  @Override
  public List<QualityViolation> check(QualityContext context) {
    var violations = new ArrayList<QualityViolation>();
    for (var source : context.sources().sources()) {
      new Scanner(context, source, violations).scan(source.unit(), null);
    }
    return violations;
  }

  /** 遍历注解节点并报告源码中的 PMD 抑制声明。 */
  private static final class Scanner extends TreePathScanner<Void, Void> {
    private final QualityContext context;
    private final ParsedSource source;
    private final List<QualityViolation> violations;

    private Scanner(
        QualityContext context, ParsedSource source, List<QualityViolation> violations) {
      this.context = context;
      this.source = source;
      this.violations = violations;
    }

    @Override
    public Void visitAnnotation(AnnotationTree tree, Void unused) {
      if (tree.getAnnotationType().toString().endsWith("SuppressWarnings")) {
        var matcher = PMD_RULE.matcher(tree.toString());
        while (matcher.find()) {
          var rule = matcher.group(1);
          if (BACKGROUND_SCANNER.equals(source.relativePath())
              && "PMD.CloseResource".equals(rule)) {
            continue;
          }
          var position =
              context
                  .sources()
                  .docTrees()
                  .getSourcePositions()
                  .getStartPosition(source.unit(), tree);
          var line = (int) source.unit().getLineMap().getLineNumber(position);
          violations.add(
              new QualityViolation(
                  ID,
                  source.relativePath(),
                  line,
                  "PMD_SUPPRESSION_FORBIDDEN",
                  "不得用 @SuppressWarnings 压制 " + rule,
                  Map.of("pmdRule", rule)));
        }
      }
      return super.visitAnnotation(tree, unused);
    }
  }
}
