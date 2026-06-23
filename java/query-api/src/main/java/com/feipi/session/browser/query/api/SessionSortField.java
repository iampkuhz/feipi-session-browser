package com.feipi.session.browser.query.api;

import java.util.Objects;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 会话列表排序字段枚举。
 *
 * <p>限定允许的排序列，防止 SQL 注入。每个枚举常量对应 {@code sessions} 表的一个索引列或可排序列。 不允许的列无法通过本枚举表达，从而在编译期排除非法输入。
 */
@Getter
@RequiredArgsConstructor
public enum SessionSortField {
  /** 按末事件时间排序，对应 {@code ended_at} 列。 */
  ENDED_AT("ended_at"),

  /** 按首事件时间排序，对应 {@code started_at} 列。 */
  STARTED_AT("started_at"),

  /** 按非缓存输入 token 量排序，对应 {@code fresh_input_tokens} 列。 */
  FRESH_INPUT_TOKENS("fresh_input_tokens"),

  /** 按 token 总量排序，对应 {@code total_tokens} 列。 */
  TOTAL_TOKENS("total_tokens"),

  /** 按助手消息数排序，对应 {@code assistant_message_count} 列。 */
  ASSISTANT_MESSAGE_COUNT("assistant_message_count"),

  /** 按工具调用数排序，对应 {@code tool_call_count} 列。 */
  TOOL_CALL_COUNT("tool_call_count"),

  /** 按会话墙钟时长排序，对应 {@code duration_seconds} 列。 */
  DURATION_SECONDS("duration_seconds"),

  /** 按模型推理时长排序，对应 {@code model_execution_seconds} 列。 */
  MODEL_EXECUTION_SECONDS("model_execution_seconds"),

  /** 按工具执行时长排序，对应 {@code tool_execution_seconds} 列。 */
  TOOL_EXECUTION_SECONDS("tool_execution_seconds"),

  /** 按失败工具数排序，对应 {@code failed_tool_count} 列。 */
  FAILED_TOOL_COUNT("failed_tool_count"),

  /** 按子 agent 实例数排序，对应 {@code subagent_instance_count} 列。 */
  SUBAGENT_INSTANCE_COUNT("subagent_instance_count");

  /** 对应 {@code sessions} 表列名，用于 SQL 拼接。 */
  private final String columnName;

  /**
   * 将字符串解析为排序字段。
   *
   * <p>按列名匹配，不区分大小写。
   *
   * @param value 排序字段字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值无法匹配任何合法字段时
   */
  public static SessionSortField fromString(String value) {
    Objects.requireNonNull(value, "排序字段不得为 null");
    for (SessionSortField field : values()) {
      if (field.getColumnName().equalsIgnoreCase(value) || field.name().equalsIgnoreCase(value)) {
        return field;
      }
    }
    throw new IllegalArgumentException("无法识别的会话排序字段: " + value);
  }
}
