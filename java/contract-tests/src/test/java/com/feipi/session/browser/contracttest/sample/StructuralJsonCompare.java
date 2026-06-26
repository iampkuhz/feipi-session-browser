package com.feipi.session.browser.contracttest.sample;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * 结构化的 JSON 比较器。
 *
 * <p>使用 Jackson 解析两个 JSON 字符串为 JsonNode，递归比较结构差异， 返回差异列表。
 */
public final class StructuralJsonCompare {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  private StructuralJsonCompare() {}

  /**
   * 比较两个 JSON 字符串的结构差异。
   *
   * @param expected 期望的 JSON
   * @param actual 实际的 JSON
   * @return 差异列表，空列表表示完全匹配
   */
  public static List<String> compare(String expected, String actual) {
    List<String> differences = new ArrayList<>();
    try {
      JsonNode expectedNode = MAPPER.readTree(expected);
      JsonNode actualNode = MAPPER.readTree(actual);
      compareNodes("$", expectedNode, actualNode, differences);
    } catch (IOException e) {
      differences.add("JSON 解析失败: " + e.getMessage());
    }
    return differences;
  }

  private static void compareNodes(
      String path, JsonNode expected, JsonNode actual, List<String> differences) {
    if (expected == null && actual == null) {
      return;
    }
    if (expected == null) {
      differences.add(path + ": 期望为 null，但实际存在");
      return;
    }
    if (actual == null) {
      differences.add(path + ": 期望存在，但实际为 null");
      return;
    }

    if (expected.getNodeType() != actual.getNodeType()) {
      differences.add(
          path
              + ": 节点类型不匹配，期望 "
              + expected.getNodeType()
              + "，实际 "
              + actual.getNodeType());
      return;
    }

    if (expected.isObject()) {
      compareObjects(path, (ObjectNode) expected, (ObjectNode) actual, differences);
    } else if (expected.isArray()) {
      compareArrays(path, (ArrayNode) expected, (ArrayNode) actual, differences);
    } else if (!expected.equals(actual)) {
      differences.add(path + ": 值不匹配，期望 " + expected + "，实际 " + actual);
    }
  }

  private static void compareObjects(
      String path, ObjectNode expected, ObjectNode actual, List<String> differences) {
    Iterator<Map.Entry<String, JsonNode>> fields = expected.fields();
    while (fields.hasNext()) {
      Map.Entry<String, JsonNode> entry = fields.next();
      String fieldName = entry.getKey();
      JsonNode expectedValue = entry.getValue();
      JsonNode actualValue = actual.get(fieldName);

      if (actualValue == null) {
        differences.add(path + "." + fieldName + ": 期望存在，但实际缺失");
      } else {
        compareNodes(path + "." + fieldName, expectedValue, actualValue, differences);
      }
    }

    fields = actual.fields();
    while (fields.hasNext()) {
      Map.Entry<String, JsonNode> entry = fields.next();
      String fieldName = entry.getKey();
      if (!expected.has(fieldName)) {
        differences.add(path + "." + fieldName + ": 实际存在，但期望缺失");
      }
    }
  }

  private static void compareArrays(
      String path, ArrayNode expected, ArrayNode actual, List<String> differences) {
    if (expected.size() != actual.size()) {
      differences.add(
          path + ": 数组长度不匹配，期望 " + expected.size() + "，实际 " + actual.size());
    }

    int minSize = Math.min(expected.size(), actual.size());
    for (int i = 0; i < minSize; i++) {
      compareNodes(path + "[" + i + "]", expected.get(i), actual.get(i), differences);
    }
  }
}
