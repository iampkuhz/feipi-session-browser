package com.feipi.session.browser.quality.gates.core;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 稳定 JSON summary 生成器；字段顺序是 CLI contract 的一部分。 */
public final class QualitySummary {

  private QualitySummary() {}

  /**
   * 生成聚合执行报告；每条规则必须携带自身候选数，不能用其他规则的候选推断状态。
   *
   * @param candidateCount 去重后的全局候选数。
   * @param executions 按规则选择顺序保存的执行结果。
   * @return 字段顺序稳定的 JSON 报告。
   */
  public static String json(int candidateCount, List<RuleExecution> executions) {
    executions = List.copyOf(executions);
    if (candidateCount < 0 || executions.isEmpty()) {
      throw new IllegalArgumentException("candidate count must be non-negative with executions");
    }
    var allRulesHaveNoCandidates =
        executions.stream().allMatch(execution -> execution.candidateCount() == 0);
    if ((candidateCount == 0) != allRulesHaveNoCandidates) {
      throw new IllegalArgumentException("global and rule candidate counts are inconsistent");
    }
    var violations =
        executions.stream().flatMap(execution -> execution.violations().stream()).toList();
    var advisories =
        executions.stream().flatMap(execution -> execution.advisories().stream()).toList();
    var status = "FAILED";
    if (violations.isEmpty()) {
      status = allRulesHaveNoCandidates ? "NOT_APPLICABLE" : "PASSED";
    }
    var output = new StringBuilder();
    output
        .append("{\"status\":")
        .append(string(status))
        .append(",\"candidateCount\":")
        .append(candidateCount)
        .append(",\"rules\":[");
    for (int index = 0; index < executions.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      var execution = executions.get(index);
      var ruleStatus =
          execution.candidateCount() == 0
              ? "NOT_APPLICABLE"
              : execution.violations().isEmpty() ? "PASSED" : "FAILED";
      output
          .append("{\"rule\":")
          .append(string(execution.rule()))
          .append(",\"status\":")
          .append(string(ruleStatus))
          .append(",\"candidateCount\":")
          .append(execution.candidateCount())
          .append(",\"violationCount\":")
          .append(execution.violations().size())
          .append(",\"advisoryCount\":")
          .append(execution.advisories().size())
          .append('}');
    }
    output.append("],\"violations\":[");
    for (int index = 0; index < violations.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      appendDiagnostic(output, JsonDiagnostic.from(violations.get(index)));
    }
    output.append("],\"advisories\":[");
    for (int index = 0; index < advisories.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      appendDiagnostic(output, JsonDiagnostic.from(advisories.get(index)));
    }
    return output.append("]}\n").toString();
  }

  /**
   * 保存一条已选择规则自己的候选数与违规；禁止用其他规则的候选推断状态。
   *
   * @param rule 稳定规则标识。
   * @param candidateCount 该规则实际收到的源码文件数。
   * @param violations 该规则按自身扫描语义产生的稳定阻断诊断顺序。
   * @param advisories 该规则按自身扫描语义产生的稳定非阻断建议顺序。
   */
  public record RuleExecution(
      String rule,
      int candidateCount,
      List<QualityViolation> violations,
      List<QualityAdvisory> advisories) {

    /** 普通规则没有建议项，继续使用简洁的三参数构造。 */
    public RuleExecution(String rule, int candidateCount, List<QualityViolation> violations) {
      this(rule, candidateCount, violations, List.of());
    }

    /** 校验候选与违规归属并做防御性复制。 */
    public RuleExecution {
      Objects.requireNonNull(rule, "rule");
      violations = List.copyOf(violations);
      advisories = List.copyOf(advisories);
      if (rule.isBlank() || candidateCount < 0) {
        throw new IllegalArgumentException("rule and candidate count must be valid");
      }
      if (candidateCount == 0 && (!violations.isEmpty() || !advisories.isEmpty())) {
        throw new IllegalArgumentException("zero-candidate rule cannot contain diagnostics");
      }
      if (violations.stream().anyMatch(violation -> !violation.rule().equals(rule))) {
        throw new IllegalArgumentException("violation must belong to its rule execution");
      }
      if (advisories.stream().anyMatch(advisory -> !advisory.rule().equals(rule))) {
        throw new IllegalArgumentException("advisory must belong to its rule execution");
      }
    }
  }

  /** 统一写出阻断项与建议项，避免两类诊断的 JSON contract 漂移。 */
  private static void appendDiagnostic(StringBuilder output, JsonDiagnostic item) {
    output
        .append("{\"rule\":")
        .append(string(item.rule()))
        .append(",\"path\":")
        .append(string(item.path()))
        .append(",\"line\":")
        .append(item.line())
        .append(",\"code\":")
        .append(string(item.code()))
        .append(",\"message\":")
        .append(string(item.message()))
        .append(",\"attributes\":{");
    var attributes = item.attributes().entrySet().stream().sorted(MapEntry.COMPARATOR).toList();
    for (int index = 0; index < attributes.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      var attribute = attributes.get(index);
      output.append(string(attribute.getKey())).append(':').append(string(attribute.getValue()));
    }
    output.append("}}");
  }

  /**
   * JSON writer 的内部诊断视图。
   *
   * @param rule 规则 id。
   * @param path 仓库相对路径。
   * @param line 诊断行号。
   * @param code 稳定诊断代码。
   * @param message 用户可读说明。
   * @param attributes 附加属性。
   */
  private record JsonDiagnostic(
      String rule,
      String path,
      int line,
      String code,
      String message,
      Map<String, String> attributes) {

    private static JsonDiagnostic from(QualityViolation item) {
      return new JsonDiagnostic(
          item.rule(), item.path(), item.line(), item.code(), item.message(), item.attributes());
    }

    private static JsonDiagnostic from(QualityAdvisory item) {
      return new JsonDiagnostic(
          item.rule(), item.path(), item.line(), item.code(), item.message(), item.attributes());
    }
  }

  private static String string(String value) {
    var output = new StringBuilder("\"");
    for (var character : value.toCharArray()) {
      switch (character) {
        case '"' -> output.append("\\\"");
        case '\\' -> output.append("\\\\");
        case '\n' -> output.append("\\n");
        case '\r' -> output.append("\\r");
        case '\t' -> output.append("\\t");
        default -> output.append(character);
      }
    }
    return output.append('"').toString();
  }

  /** 按属性键稳定排序，保证质量摘要在重复运行时保持确定顺序。 */
  private static final class MapEntry {
    private static final Comparator<Map.Entry<String, String>> COMPARATOR =
        Map.Entry.comparingByKey();

    private MapEntry() {}
  }
}
