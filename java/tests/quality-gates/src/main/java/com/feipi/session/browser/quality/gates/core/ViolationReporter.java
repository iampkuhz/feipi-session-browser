package com.feipi.session.browser.quality.gates.core;

import java.io.IOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * 违规报告输出工具。
 *
 * <p>支持 text 和 json 两种输出格式，以及报告文件写入。
 */
public final class ViolationReporter {

  private ViolationReporter() {}

  /**
   * 将违规列表格式化为 text 格式。
   *
   * <p>格式为 {@code path:line: CODE: message}，兼容旧 Python 脚本输出。
   *
   * @param violations 违规列表。
   * @return 格式化后的字符串。
   */
  public static String formatText(List<QualityViolation> violations) {
    var sb = new StringBuilder();
    for (var violation : violations) {
      sb.append(violation.path())
          .append(':')
          .append(violation.line())
          .append(": ")
          .append(violation.code())
          .append(": ")
          .append(violation.message())
          .append(System.lineSeparator());
    }
    return sb.toString();
  }

  /**
   * 将违规列表格式化为 JSON 数组。
   *
   * @param violations 违规列表。
   * @return JSON 字符串。
   */
  public static String formatJson(List<QualityViolation> violations) {
    var sb = new StringBuilder();
    sb.append('[');
    for (int i = 0; i < violations.size(); i++) {
      if (i > 0) {
        sb.append(',');
      }
      var v = violations.get(i);
      sb.append("\n  {")
          .append("\"path\":")
          .append(jsonString(v.path().toString()))
          .append(",\"line\":")
          .append(v.line())
          .append(",\"code\":")
          .append(jsonString(v.code()))
          .append(",\"message\":")
          .append(jsonString(v.message()))
          .append(",\"attributes\":{");
      var attrs = v.attributes();
      var keys = attrs.keySet().toArray(new String[0]);
      for (int j = 0; j < keys.length; j++) {
        if (j > 0) {
          sb.append(',');
        }
        sb.append(jsonString(keys[j])).append(':').append(jsonString(attrs.get(keys[j])));
      }
      sb.append("}}");
    }
    if (!violations.isEmpty()) {
      sb.append('\n');
    }
    sb.append(']');
    return sb.toString();
  }

  /**
   * 将违规报告写入文件。
   *
   * @param violations 违规列表。
   * @param reportFile 报告文件路径。
   * @param format 输出格式（text 或 json）。
   * @throws IOException 写入失败时抛出。
   */
  public static void writeReport(List<QualityViolation> violations, Path reportFile, String format)
      throws IOException {
    var parent = reportFile.getParent();
    if (parent != null) {
      Files.createDirectories(parent);
    }
    try (Writer writer = Files.newBufferedWriter(reportFile, StandardCharsets.UTF_8)) {
      if (violations.isEmpty()) {
        writer.write("PASSED\n");
      } else {
        writer.write(formatText(violations));
      }
    }
  }

  private static String jsonString(String value) {
    if (value == null) {
      return "null";
    }
    var sb = new StringBuilder("\"");
    for (int i = 0; i < value.length(); i++) {
      var ch = value.charAt(i);
      switch (ch) {
        case '"' -> sb.append("\\\"");
        case '\\' -> sb.append("\\\\");
        case '\n' -> sb.append("\\n");
        case '\r' -> sb.append("\\r");
        case '\t' -> sb.append("\\t");
        default -> sb.append(ch);
      }
    }
    sb.append('"');
    return sb.toString();
  }
}
