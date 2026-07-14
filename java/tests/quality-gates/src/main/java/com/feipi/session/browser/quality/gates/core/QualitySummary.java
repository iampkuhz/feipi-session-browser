package com.feipi.session.browser.quality.gates.core;

import java.util.Comparator;
import java.util.List;

/** 稳定 JSON summary 生成器；字段顺序是 CLI contract 的一部分。 */
public final class QualitySummary {

  private QualitySummary() {}

  /** 生成聚合执行报告。 */
  public static String json(
      String status, int candidateCount, List<String> selectedRules, List<QualityViolation> input) {
    var violations =
        input.stream()
            .sorted(
                Comparator.comparing(QualityViolation::path)
                    .thenComparingInt(QualityViolation::line)
                    .thenComparing(QualityViolation::rule)
                    .thenComparing(QualityViolation::code)
                    .thenComparing(item -> item.attributes().toString()))
            .toList();
    var output = new StringBuilder();
    output
        .append("{\"status\":")
        .append(string(status))
        .append(",\"candidateCount\":")
        .append(candidateCount)
        .append(",\"rules\":[");
    for (int index = 0; index < selectedRules.size(); index++) {
      if (index > 0) {
        output.append(',');
      }
      var rule = selectedRules.get(index);
      var count = violations.stream().filter(item -> item.rule().equals(rule)).count();
      var ruleStatus = "NOT_APPLICABLE".equals(status) ? status : count == 0 ? "PASSED" : "FAILED";
      output
          .append("{\"rule\":")
          .append(string(rule))
          .append(",\"status\":")
          .append(string(ruleStatus))
          .append(",\"violationCount\":")
          .append(count)
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

  private static final class MapEntry {
    private static final Comparator<java.util.Map.Entry<String, String>> COMPARATOR =
        java.util.Map.Entry.comparingByKey();

    private MapEntry() {}
  }
}
