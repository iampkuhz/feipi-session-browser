package com.feipi.session.browser.quality.gates.core;

import java.util.Comparator;
import java.util.List;
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
        executions.stream()
            .flatMap(execution -> execution.violations().stream())
            .sorted(
                Comparator.comparing(QualityViolation::path)
                    .thenComparingInt(QualityViolation::line)
                    .thenComparing(QualityViolation::rule)
                    .thenComparing(QualityViolation::code)
                    .thenComparing(item -> item.attributes().toString()))
            .toList();
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
          .append('}');
    }
    output.append("],\"violations\":[");
    for (int index = 0; index < violations.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      var item = violations.get(index);
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
      for (int attributeIndex = 0; attributeIndex < attributes.size(); attributeIndex++) {
        if (attributeIndex > 0) {
          output.append(',');
        }
        var attribute = attributes.get(attributeIndex);
        output.append(string(attribute.getKey())).append(':').append(string(attribute.getValue()));
      }
      output.append("}}");
    }
    return output.append("]}\n").toString();
  }

  /**
   * 保存一条已选择规则自己的候选数与违规；禁止用其他规则的候选推断状态。
   *
   * @param rule 稳定规则标识。
   * @param candidateCount 该规则实际收到的源码文件数。
   * @param violations 该规则产生的违规。
   */
  public record RuleExecution(String rule, int candidateCount, List<QualityViolation> violations) {

    /** 校验候选与违规归属并做防御性复制。 */
    public RuleExecution {
      Objects.requireNonNull(rule, "rule");
      violations = List.copyOf(violations);
      if (rule.isBlank() || candidateCount < 0) {
        throw new IllegalArgumentException("rule and candidate count must be valid");
      }
      if (candidateCount == 0 && !violations.isEmpty()) {
        throw new IllegalArgumentException("zero-candidate rule cannot contain violations");
      }
      if (violations.stream().anyMatch(violation -> !violation.rule().equals(rule))) {
        throw new IllegalArgumentException("violation must belong to its rule execution");
      }
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
    private static final Comparator<java.util.Map.Entry<String, String>> COMPARATOR =
        java.util.Map.Entry.comparingByKey();

    private MapEntry() {}
  }
}
