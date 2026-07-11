package com.feipi.session.browser.quality.gates.rules.record;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Javadoc {@code @param} 解析器。
 *
 * <p>从 Javadoc 文本中提取 {@code @param name description} 映射， 支持跨行描述，跳过类型参数 {@code @param <T>}。
 */
final class ParamDocParser {

  private static final Pattern PARAM_PATTERN =
      Pattern.compile("@param\\s+([A-Za-z_$][A-Za-z0-9_$]*|<[^>]+>)\\s*(.*)$");
  private static final Pattern STAR_PREFIX = Pattern.compile("^\\s*\\*\\s?");

  private ParamDocParser() {}

  /**
   * 解析 Javadoc 中的 {@code @param} 条目。
   *
   * @param javadocText Javadoc 注释原文（含 {@code /**} 和 {@code * /}）。
   * @return 参数名到描述文本的映射；类型参数也会包含但不会被 gate 误认为 component。
   */
  static Map<String, String> parse(String javadocText) {
    var body = javadocText;
    if (body.startsWith("/**")) {
      body = body.substring(3);
    }
    if (body.endsWith("*/")) {
      body = body.substring(0, body.length() - 2);
    }

    var params = new LinkedHashMap<String, java.util.List<String>>();
    String current = null;

    for (var raw : body.split("\\r?\\n")) {
      var line = STAR_PREFIX.matcher(raw).replaceFirst("").trim();
      if (line.isEmpty()) {
        continue;
      }

      var paramMatch = PARAM_PATTERN.matcher(line);
      if (paramMatch.matches()) {
        current = paramMatch.group(1);
        params.computeIfAbsent(current, k -> new java.util.ArrayList<>());
        var desc = paramMatch.group(2).trim();
        if (!desc.isEmpty()) {
          params.get(current).add(desc);
        }
        continue;
      }

      if (line.startsWith("@")) {
        current = null;
        continue;
      }

      if (current != null) {
        params.get(current).add(line);
      }
    }

    var result = new LinkedHashMap<String, String>();
    for (var entry : params.entrySet()) {
      result.put(entry.getKey(), String.join(" ", entry.getValue()).trim());
    }
    return result;
  }
}
