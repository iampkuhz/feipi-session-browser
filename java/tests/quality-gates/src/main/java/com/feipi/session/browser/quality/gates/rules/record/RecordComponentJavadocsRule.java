package com.feipi.session.browser.quality.gates.rules.record;

import com.feipi.session.browser.quality.gates.core.JavaSourceSet.ParsedSource;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.QualityRule;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.sun.source.doctree.ParamTree;
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.TreePathScanner;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 使用 compiler AST 与 DocTrees 检查 record component Javadoc。 */
public final class RecordComponentJavadocsRule implements QualityRule {

  private static final String ID = "record-component-javadocs";
  private static final Pattern CHINESE =
      Pattern.compile("[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff]");

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
    public Void visitClass(ClassTree tree, Void unused) {
      if (tree.getKind() == Tree.Kind.RECORD) {
        inspect(tree);
      }
      return super.visitClass(tree, unused);
    }

    private void inspect(ClassTree tree) {
      var positions = context.sources().docTrees().getSourcePositions();
      var doc = context.sources().docTrees().getDocCommentTree(getCurrentPath());
      var recordName = tree.getSimpleName().toString();
      var line = line(positions.getStartPosition(source.unit(), tree));
      if (doc == null) {
        violations.add(
            violation(
                line,
                "RECORD_JAVADOC_MISSING",
                "record " + recordName + " 缺少类型 Javadoc，无法说明 components",
                Map.of("record", recordName)));
        return;
      }
      var descriptions = new LinkedHashMap<String, String>();
      for (var tag : doc.getBlockTags()) {
        if (tag instanceof ParamTree param && !param.isTypeParameter()) {
          var description = new StringBuilder();
          for (var part : param.getDescription()) {
            var start = positions.getStartPosition(source.unit(), doc, part);
            var end = positions.getEndPosition(source.unit(), doc, part);
            if (start >= 0 && end >= start) {
              description.append(source.text(), (int) start, (int) end).append(' ');
            } else {
              description.append(part).append(' ');
            }
          }
          descriptions.put(param.getName().toString(), description.toString().trim());
        }
      }
      var headerEnd =
          source.text().indexOf('{', (int) positions.getStartPosition(source.unit(), tree));
      for (var member : tree.getMembers()) {
        if (!(member instanceof VariableTree component)) {
          continue;
        }
        var start = positions.getStartPosition(source.unit(), component);
        if (start < 0 || start >= headerEnd) {
          continue;
        }
        var componentName = component.getName().toString();
        var description = descriptions.get(componentName);
        if (description == null) {
          violations.add(
              violation(
                  line(start),
                  "RECORD_COMPONENT_PARAM_MISSING",
                  "record " + recordName + " component " + componentName + " 缺少 @param 说明",
                  Map.of("record", recordName, "component", componentName)));
        } else if (!CHINESE.matcher(description).find()) {
          violations.add(
              violation(
                  line(start),
                  "RECORD_COMPONENT_PARAM_NOT_CHINESE",
                  "record " + recordName + " component " + componentName + " 的 @param 说明必须包含中文",
                  Map.of("record", recordName, "component", componentName)));
        }
      }
    }

    private int line(long position) {
      return (int) source.unit().getLineMap().getLineNumber(position);
    }

    private QualityViolation violation(
        int line, String code, String message, Map<String, String> attributes) {
      return new QualityViolation(ID, source.relativePath(), line, code, message, attributes);
    }
  }
}
