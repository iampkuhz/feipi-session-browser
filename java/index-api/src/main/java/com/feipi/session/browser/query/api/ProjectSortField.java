package com.feipi.session.browser.query.api;

import java.util.Objects;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 项目列表排序字段枚举。
 *
 * <p>限定允许的排序列，防止 SQL 注入。每个枚举常量对应项目查询结果的一个可排序维度。
 */
@Getter
@RequiredArgsConstructor
public enum ProjectSortField {
  /** 按会话总数排序。 */
  TOTAL_SESSIONS("total_sessions"),

  /** 按 token 总量排序。 */
  TOTAL_TOKENS("total_tokens"),

  /** 按工具调用总数排序。 */
  TOTAL_TOOL_CALLS("total_tool_calls"),

  /** 按失败工具总数排序。 */
  TOTAL_FAILED_TOOLS("total_failed_tools"),

  /** 按首次出现时间排序。 */
  FIRST_SEEN("first_seen"),

  /** 按最近活跃时间排序。 */
  LAST_ACTIVE("last_active");

  /** 排序维度标识，用于 SQL 排序表达式。 */
  private final String sortKey;

  /**
   * 获取稳定外部协议值。
   *
   * <p>委托给 {@code getSortKey()}，保持与其他枚举的 {@code getValue()} 接口一致。
   *
   * @return 外部协议字符串值
   */
  public String getValue() {
    return sortKey;
  }

  /**
   * 从外部协议值解析排序字段。
   *
   * <p>委托给 {@link #fromString(String)}，保持与其他枚举的 {@code fromValue()} 接口一致。
   *
   * @param value 外部协议字符串值
   * @return 对应的排序字段枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知字段
   * @throws NullPointerException 如果值为 null
   */
  public static ProjectSortField fromValue(String value) {
    return fromString(value);
  }

  /**
   * 将字符串解析为排序字段。
   *
   * <p>按 sortKey 或枚举名匹配，不区分大小写。
   *
   * @param value 排序字段字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值无法匹配任何合法字段时
   */
  public static ProjectSortField fromString(String value) {
    Objects.requireNonNull(value, "排序字段不得为 null");
    for (ProjectSortField field : values()) {
      if (field.getSortKey().equalsIgnoreCase(value) || field.name().equalsIgnoreCase(value)) {
        return field;
      }
    }
    throw new IllegalArgumentException("无法识别的项目排序字段: " + value);
  }
}
