package com.feipi.session.browser.domain.normalized;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * 四段 token 的计量来源，独立于数值；真实上报的 0 不等于未上报。
 *
 * <p>三个覆盖数统计参与会话中任一段包含对应状态的会话数量，可互相重叠。mixed 的原始组成通过覆盖数保留。
 *
 * @param freshInput 新鲜输入精度
 * @param cacheRead 缓存读取精度
 * @param cacheWrite 缓存写入精度
 * @param output 输出精度
 * @param estimationMethod 非秘密的估算法名称，多算法以逗号分隔
 * @param estimatedSessionCount 含估算的会话覆盖数
 * @param unavailableSessionCount 含未上报字段的会话覆盖数
 * @param unknownSessionCount 含未知精度的会话覆盖数
 */
public record TokenProvenance(
    String freshInput,
    String cacheRead,
    String cacheWrite,
    String output,
    String estimationMethod,
    long estimatedSessionCount,
    long unavailableSessionCount,
    long unknownSessionCount) {

  private static final Set<String> PRECISIONS =
      Set.of("provider_reported", "estimated", "unavailable", "unknown", "mixed");

  /** 规范化缺失/非法状态为 unknown，覆盖数不得为负。 */
  public TokenProvenance {
    freshInput = precision(freshInput);
    cacheRead = precision(cacheRead);
    cacheWrite = precision(cacheWrite);
    output = precision(output);
    estimationMethod = estimationMethod == null ? "" : estimationMethod;
    if (estimatedSessionCount < 0 || unavailableSessionCount < 0 || unknownSessionCount < 0) {
      throw new IllegalArgumentException("Token provenance coverage must be nonnegative");
    }
  }

  /** 旧消费者或旧制品的单会话未知状态。 */
  public static TokenProvenance unknown() {
    return unknown(1);
  }

  /** 为已知参与会话数保留未知精度。 */
  public static TokenProvenance unknown(long sessionCount) {
    return new TokenProvenance("unknown", "unknown", "unknown", "unknown", "", 0, 0, sessionCount);
  }

  /** 无参与会话的合并恒等元，不引入 unknown 覆盖。 */
  public static TokenProvenance empty() {
    return unknown(0);
  }

  /** 从 candidate 或 artifact session 的扁平元数据读取单会话精度。 */
  public static TokenProvenance fromMetadata(Map<String, ?> metadata) {
    String fresh = precision(value(metadata, "freshInputTokenPrecision"));
    String read = precision(value(metadata, "cacheReadTokenPrecision"));
    String write = precision(value(metadata, "cacheWriteTokenPrecision"));
    String out = precision(value(metadata, "outputTokenPrecision"));
    Set<String> states = Set.copyOf(java.util.List.of(fresh, read, write, out));
    String method = value(metadata, "tokenEstimationMethod");
    return new TokenProvenance(
        fresh,
        read,
        write,
        out,
        method,
        states.contains("estimated")
                || !method.isBlank()
                || flag(metadata, "tokenContainsEstimated")
            ? 1
            : 0,
        states.contains("unavailable") || flag(metadata, "tokenContainsUnavailable") ? 1 : 0,
        states.contains("unknown") || flag(metadata, "tokenContainsUnknown") ? 1 : 0);
  }

  /** 写回 artifact session 的兼容扁平字段，不改顶层 artifact schema。 */
  public Map<String, Object> toMetadata() {
    Map<String, Object> metadata = new LinkedHashMap<>();
    metadata.put("freshInputTokenPrecision", freshInput);
    metadata.put("cacheReadTokenPrecision", cacheRead);
    metadata.put("cacheWriteTokenPrecision", cacheWrite);
    metadata.put("outputTokenPrecision", output);
    metadata.put("tokenEstimationMethod", estimationMethod);
    metadata.put("tokenContainsEstimated", estimatedSessionCount > 0);
    metadata.put("tokenContainsUnavailable", unavailableSessionCount > 0);
    metadata.put("tokenContainsUnknown", unknownSessionCount > 0);
    return Map.copyOf(metadata);
  }

  /** 合并互不重叠的参与会话集合；相同状态保留，异状态为 mixed。 */
  public TokenProvenance plus(TokenProvenance other) {
    if (equals(empty())) {
      return other;
    }
    if (other.equals(empty())) {
      return this;
    }
    Set<String> methods = new LinkedHashSet<>();
    for (String method : (estimationMethod + "," + other.estimationMethod).split(",")) {
      if (!method.isBlank()) {
        methods.add(method);
      }
    }
    return new TokenProvenance(
        merge(freshInput, other.freshInput),
        merge(cacheRead, other.cacheRead),
        merge(cacheWrite, other.cacheWrite),
        merge(output, other.output),
        String.join(",", methods),
        estimatedSessionCount + other.estimatedSessionCount,
        unavailableSessionCount + other.unavailableSessionCount,
        unknownSessionCount + other.unknownSessionCount);
  }

  /** 合并两个计量来源；不一致时保留混合状态。 */
  private static String merge(String left, String right) {
    return left.equals(right) ? left : "mixed";
  }

  /** 将缺失或不支持的来源值归为未知。 */
  private static String precision(String value) {
    return value != null && PRECISIONS.contains(value) ? value : "unknown";
  }

  /** 读取来源元数据的文本值，缺失时返回空串。 */
  private static String value(Map<String, ?> metadata, String key) {
    Object value = metadata.get(key);
    return value == null ? "" : value.toString();
  }

  /** 读取来源元数据中的布尔标记。 */
  private static boolean flag(Map<String, ?> metadata, String key) {
    return Boolean.parseBoolean(value(metadata, key));
  }
}
