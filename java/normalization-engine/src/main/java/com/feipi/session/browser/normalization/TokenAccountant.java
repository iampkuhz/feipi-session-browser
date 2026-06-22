package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;

/**
 * Token 核算器。
 *
 * <p>从 JSON 事件的 {@code usage} 字段提取 token 用量信息，构建 {@link NormalizedCallUsage} 实例。
 *
 * <p>识别的字段名：
 *
 * <ul>
 *   <li>{@code input_tokens} — 输入 token 数，映射为 {@code fresh}
 *   <li>{@code cache_read_input_tokens} — 缓存读取 token 数，映射为 {@code cacheRead}
 *   <li>{@code cache_creation_input_tokens} — 缓存写入 token 数，映射为 {@code cacheWrite}
 *   <li>{@code output_tokens} — 输出 token 数，映射为 {@code output}
 * </ul>
 *
 * <p>{@code total} 始终由分量之和计算，保证 {@link NormalizedCallUsage} 不变量。
 */
public final class TokenAccountant {

  /** 防止实例化。 */
  private TokenAccountant() {}

  /**
   * 从事件的 {@code usage} 字段提取 token 用量。
   *
   * <p>如果事件没有 {@code usage} 字段或该字段不是对象，返回全零的用量实例。 缺失的 token 分量默认为 0。
   *
   * @param event JSON 事件节点
   * @return 不可变的 token 用量实例
   */
  public static NormalizedCallUsage extractUsage(JsonNode event) {
    if (event == null) {
      return NormalizedCallUsage.empty();
    }
    JsonNode usageNode = event.get("usage");
    if (usageNode == null || !usageNode.isObject()) {
      return NormalizedCallUsage.empty();
    }
    long fresh = readLong(usageNode, "input_tokens");
    long cacheRead = readLong(usageNode, "cache_read_input_tokens");
    long cacheWrite = readLong(usageNode, "cache_creation_input_tokens");
    long output = readLong(usageNode, "output_tokens");
    long total = fresh + cacheRead + cacheWrite + output;
    return new NormalizedCallUsage(fresh, cacheRead, cacheWrite, output, total);
  }

  private static long readLong(JsonNode node, String fieldName) {
    JsonNode child = node.get(fieldName);
    if (child != null && child.isNumber()) {
      return child.asLong();
    }
    return 0L;
  }
}
