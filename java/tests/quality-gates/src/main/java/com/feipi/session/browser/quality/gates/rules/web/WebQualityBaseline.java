package com.feipi.session.browser.quality.gates.rules.web;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 读取多个 Web 质量规则共用的单文件基线；不负责扫描资源或生成违规。 */
final class WebQualityBaseline {

  private static final ObjectMapper MAPPER =
      new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

  private final Map<String, Map<String, List<String>>> rules;

  private WebQualityBaseline(Map<String, Map<String, List<String>>> rules) {
    this.rules = Map.copyOf(rules);
  }

  /**
   * 加载基线；文件缺失、JSON 损坏或 section 类型错误时按旧 Python owner 的空基线语义处理。
   *
   * <p>空基线不会放行扫描结果，因此存量违规会重新成为阻断项。
   */
  static WebQualityBaseline load(Path path) {
    try {
      var root = MAPPER.readTree(path.toFile());
      if (root == null || !root.isObject()) {
        return empty();
      }
      var rulesNode = root.get("rules");
      if (rulesNode == null || !rulesNode.isObject()) {
        return empty();
      }
      var parsedRules = new LinkedHashMap<String, Map<String, List<String>>>();
      var ruleFields = rulesNode.fields();
      while (ruleFields.hasNext()) {
        var ruleField = ruleFields.next();
        if (!ruleField.getValue().isObject()) {
          return empty();
        }
        parsedRules.put(ruleField.getKey(), parseSection(ruleField.getValue()));
      }
      return new WebQualityBaseline(parsedRules);
    } catch (IOException | RuntimeException ignored) {
      return empty();
    }
  }

  /** 返回规则 section 中一个类别的稳定字符串列表；不存在时返回空列表。 */
  List<String> entries(String ruleId, String category) {
    return rules.getOrDefault(ruleId, Map.of()).getOrDefault(category, List.of());
  }

  private static Map<String, List<String>> parseSection(JsonNode section) throws IOException {
    var categories = new LinkedHashMap<String, List<String>>();
    var fields = section.fields();
    while (fields.hasNext()) {
      var field = fields.next();
      if (!field.getValue().isArray()) {
        throw new IOException("Web baseline category must be an array: " + field.getKey());
      }
      var entries = new ArrayList<String>();
      for (var value : field.getValue()) {
        if (!value.isTextual()) {
          throw new IOException("Web baseline entry must be a string: " + field.getKey());
        }
        entries.add(value.textValue());
      }
      categories.put(field.getKey(), List.copyOf(entries));
    }
    return Map.copyOf(categories);
  }

  private static WebQualityBaseline empty() {
    return new WebQualityBaseline(Map.of());
  }
}
