package com.feipi.session.browser.quality.gates.rules.record;

import com.feipi.session.browser.quality.gates.core.QualityGateContext;
import com.feipi.session.browser.quality.gates.core.QualityViolation;
import com.feipi.session.browser.quality.gates.discovery.ChangedFilesFilter;
import com.feipi.session.browser.quality.gates.discovery.FileDiscovery;
import com.feipi.session.browser.quality.gates.javaapi.JavaRecordDeclaration;
import com.feipi.session.browser.quality.gates.javaapi.JavaRecordSourceParser;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Pattern;

/**
 * record component Javadoc 检查器。
 *
 * <p>扫描 Java 源文件中的 record 声明，验证类型 Javadoc 和 {@code @param} 覆盖。
 */
public final class RecordComponentJavadocChecker {

  /** 中文字符检测正则。 */
  private static final Pattern CHINESE =
      Pattern.compile("[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff]");

  private RecordComponentJavadocChecker() {}

  /**
   * 执行检查。
   *
   * @param context 质量门上下文。
   * @return 违规列表，按 path/line/code/component 排序。
   * @throws Exception 检查过程中出现异常时抛出。
   */
  static List<QualityViolation> check(QualityGateContext context) throws Exception {
    var files = FileDiscovery.discover(context.inputPaths());
    var changedJson = context.environment().get("QUALITY_CHANGED_FILES");
    files = ChangedFilesFilter.filter(files, changedJson, context.repoRoot());
    return checkFiles(files, context);
  }

  /**
   * 对预定义文件列表执行检查（跳过 FileDiscovery 过滤）。
   *
   * <p>用于 parity 对比和直接测试。
   *
   * @param files 待检查文件列表。
   * @param context 质量门上下文。
   * @return 违规列表，按 path/line/code/component 排序。
   * @throws Exception 检查过程中出现异常时抛出。
   */
  public static List<QualityViolation> checkFiles(List<Path> files, QualityGateContext context)
      throws Exception {
    var parser = new JavaRecordSourceParser();
    var violations = new ArrayList<QualityViolation>();

    for (var file : files) {
      var records = parser.parse(file);
      for (var record : records) {
        violations.addAll(checkRecord(file, record));
      }
    }

    violations.sort(
        Comparator.comparing((QualityViolation v) -> v.path().toString())
            .thenComparingInt(QualityViolation::line)
            .thenComparing(QualityViolation::code)
            .thenComparing(v -> v.attributes().getOrDefault("component", "")));

    return violations;
  }

  private static List<QualityViolation> checkRecord(Path file, JavaRecordDeclaration record) {
    var violations = new ArrayList<QualityViolation>();

    var javadoc = record.typeJavadoc();
    if (javadoc.isEmpty()) {
      violations.add(
          new QualityViolation(
              file,
              record.line(),
              "RECORD_JAVADOC_MISSING",
              "record " + record.name() + " 缺少类型 Javadoc，无法说明 components",
              java.util.Map.of("record", record.name())));
      return violations;
    }

    var params = ParamDocParser.parse(javadoc.get());
    for (var component : record.components()) {
      var desc = params.get(component.name());
      if (desc == null) {
        violations.add(
            new QualityViolation(
                file,
                component.line(),
                "RECORD_COMPONENT_PARAM_MISSING",
                "record " + record.name() + " component " + component.name() + " 缺少 @param 说明",
                java.util.Map.of("record", record.name(), "component", component.name())));
      } else if (!CHINESE.matcher(desc).find()) {
        violations.add(
            new QualityViolation(
                file,
                component.line(),
                "RECORD_COMPONENT_PARAM_NOT_CHINESE",
                "record " + record.name() + " component " + component.name() + " 的 @param 说明必须包含中文",
                java.util.Map.of("record", record.name(), "component", component.name())));
      }
    }

    return violations;
  }
}
