package com.feipi.session.browser.source.common;

import com.fasterxml.jackson.databind.JsonNode;

/** JSON 节点读取的共享辅助方法。 */
public final class JsonNodeReaders {

  private JsonNodeReaders() {}

  /** 返回对象字段；节点为空、非对象或字段非对象时返回 null。 */
  public static JsonNode objectChild(JsonNode node, String fieldName) {
    if (node == null || !node.isObject()) {
      return null;
    }
    JsonNode child = node.get(fieldName);
    return child != null && child.isObject() ? child : null;
  }

  /** 返回文本字段；字段缺失、非文本或节点为空时返回空字符串。 */
  public static String textOrEmpty(JsonNode node, String field) {
    if (node == null || !node.isObject()) {
      return "";
    }
    JsonNode child = node.get(field);
    if (child != null && child.isTextual()) {
      return child.asText();
    }
    return "";
  }
}
