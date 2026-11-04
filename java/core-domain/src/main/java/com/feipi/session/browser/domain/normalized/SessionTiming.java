package com.feipi.session.browser.domain.normalized;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * 会话计时口径：wall、MAIN task 窗口、agent-turn workload 与模型/工具测量互不替代。
 *
 * @param wallSeconds 首末事件墙钟跨度，可能包含跨夜空闲
 * @param wallPrecision wall 的 measured/partial/unknown 状态
 * @param activeTaskSeconds 可定位的 MAIN 任务窗口并集秒数，不叠加 child
 * @param activeTaskPrecision 任务窗口完整性
 * @param activeTaskBasis 任务计时依据
 * @param agentTurnSeconds 显式 MAIN agent-turn workload 秒数，不等于模型执行或 active 墙钟
 * @param agentTurnPrecision workload 完整性
 * @param agentTurnBasis workload 计时依据
 * @param modelExecutionSeconds 显式模型执行测量，未知为 null，合法零为 0
 * @param modelExecutionPrecision 模型计时完整性
 * @param toolExecutionSeconds 显式工具执行测量，未知为 null，合法零为 0
 * @param toolExecutionPrecision 工具计时完整性
 * @param completedTaskCount 正常闭合任务数
 * @param incompleteTaskCount 不完整或无法精确配对的任务数
 * @param abortedTaskCount 已显式中止的闭合任务数
 */
public record SessionTiming(
    Double wallSeconds,
    String wallPrecision,
    Double activeTaskSeconds,
    String activeTaskPrecision,
    String activeTaskBasis,
    Double agentTurnSeconds,
    String agentTurnPrecision,
    String agentTurnBasis,
    Double modelExecutionSeconds,
    String modelExecutionPrecision,
    Double toolExecutionSeconds,
    String toolExecutionPrecision,
    long completedTaskCount,
    long incompleteTaskCount,
    long abortedTaskCount) {

  private static final Set<String> PRECISIONS = Set.of("measured", "partial", "unknown");

  /** 未知保持 null；不能把缺少计量当作实测零。 */
  public SessionTiming {
    check(wallSeconds);
    check(activeTaskSeconds);
    check(agentTurnSeconds);
    check(modelExecutionSeconds);
    check(toolExecutionSeconds);
    wallPrecision = precision(wallPrecision);
    activeTaskPrecision = precision(activeTaskPrecision);
    agentTurnPrecision = precision(agentTurnPrecision);
    modelExecutionPrecision = precision(modelExecutionPrecision);
    toolExecutionPrecision = precision(toolExecutionPrecision);
    activeTaskBasis = activeTaskBasis == null ? "" : activeTaskBasis;
    agentTurnBasis = agentTurnBasis == null ? "" : agentTurnBasis;
    if (completedTaskCount < 0 || incompleteTaskCount < 0 || abortedTaskCount < 0) {
      throw new IllegalArgumentException("Timing counts must be nonnegative");
    }
  }

  /** 旧制品/旧索引不根据历史执行数字反推计量来源。 */
  public static SessionTiming unknown(Double wallSeconds) {
    return new SessionTiming(
        wallSeconds,
        "unknown",
        null,
        "unknown",
        "",
        null,
        "unknown",
        "",
        null,
        "unknown",
        null,
        "unknown",
        0,
        0,
        0);
  }

  /** 从 artifact session 的兼容 metadata 读取计时。 */
  public static SessionTiming fromMetadata(Map<String, ?> metadata) {
    if (!(metadata.get("timing") instanceof Map<?, ?> timing)) {
      return unknown(number(metadata.get("duration_seconds")));
    }
    return new SessionTiming(
        number(timing.get("wallSeconds")),
        text(timing, "wallPrecision"),
        number(timing.get("activeTaskSeconds")),
        text(timing, "activeTaskPrecision"),
        text(timing, "activeTaskBasis"),
        number(timing.get("agentTurnSeconds")),
        text(timing, "agentTurnPrecision"),
        text(timing, "agentTurnBasis"),
        number(timing.get("modelExecutionSeconds")),
        text(timing, "modelExecutionPrecision"),
        number(timing.get("toolExecutionSeconds")),
        text(timing, "toolExecutionPrecision"),
        count(timing.get("completedTaskCount")),
        count(timing.get("incompleteTaskCount")),
        count(timing.get("abortedTaskCount")));
  }

  /** 中性 map 扩展，不改顶层 artifact/call schema；未知数值省略以兼容不可变 map。 */
  public Map<String, Object> toMetadata() {
    Map<String, Object> timing = new LinkedHashMap<>();
    put(timing, "wallSeconds", wallSeconds);
    timing.put("wallPrecision", wallPrecision);
    put(timing, "activeTaskSeconds", activeTaskSeconds);
    timing.put("activeTaskPrecision", activeTaskPrecision);
    timing.put("activeTaskBasis", activeTaskBasis);
    put(timing, "agentTurnSeconds", agentTurnSeconds);
    timing.put("agentTurnPrecision", agentTurnPrecision);
    timing.put("agentTurnBasis", agentTurnBasis);
    put(timing, "modelExecutionSeconds", modelExecutionSeconds);
    timing.put("modelExecutionPrecision", modelExecutionPrecision);
    put(timing, "toolExecutionSeconds", toolExecutionSeconds);
    timing.put("toolExecutionPrecision", toolExecutionPrecision);
    timing.put("completedTaskCount", completedTaskCount);
    timing.put("incompleteTaskCount", incompleteTaskCount);
    timing.put("abortedTaskCount", abortedTaskCount);
    return Map.of("timing", Map.copyOf(timing));
  }

  /** 仅序列化已记录的耗时，避免将未知值写成零。 */
  private static void put(Map<String, Object> values, String key, Double value) {
    if (value != null) {
      values.put(key, value);
    }
  }

  /** 将缺失或不支持的时间精度归为未知。 */
  private static String precision(String value) {
    return value != null && PRECISIONS.contains(value) ? value : "unknown";
  }

  /** 校验已记录的耗时为有限且非负的数值。 */
  private static void check(Double value) {
    if (value != null && (!Double.isFinite(value) || value < 0)) {
      throw new IllegalArgumentException("Timing values must be finite and nonnegative");
    }
  }

  /** 解析有效耗时；缺失、负数或非有限值保留未知。 */
  private static Double number(Object value) {
    return value instanceof Number number
            && Double.isFinite(number.doubleValue())
            && number.doubleValue() >= 0
        ? number.doubleValue()
        : null;
  }

  /** 读取非负事件计数，缺失时返回零。 */
  private static long count(Object value) {
    return value instanceof Number number ? Math.max(0, number.longValue()) : 0;
  }

  /** 读取时间元数据文本，不把非文本值转换为精度。 */
  private static String text(Map<?, ?> map, String key) {
    Object value = map.get(key);
    return value instanceof String text ? text : "";
  }
}
