package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Token 合计语义枚举。
 *
 * <p>描述 {@code totalTokens} 字段的计算方式。 不同的 agent source 对 token 合计有不同约定， 归一化时需要区分以正确解读 token 数据。
 */
@DomainModel
@RequiredArgsConstructor
public enum TokenTotalSemantics {
  /** 各分量之和，不含重复计数。 */
  EXCLUSIVE_COMPONENT_SUM("exclusive_components_sum"),

  /** Provider 直接上报的总计值。 */
  REPORTED_TOTAL("reported_total"),

  /** 基于累积增量差值计算的总计。 */
  REPORTED_CUMULATIVE_DELTA("reported_cumulative_delta"),

  /** 提示词总计加上输出 token 的合计。 */
  PROMPT_TOTAL_PLUS_OUTPUT("prompt_total_plus_output"),

  /** 基于估算分量的合计。 */
  ESTIMATED_COMPONENT_SUM("estimated_components_sum"),

  /** 因原始总计不一致而重新计算的分量合计。 */
  RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL("recomputed_due_to_inconsistent_raw_total");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析 token 合计语义。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的 token 合计语义枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知语义
   * @throws NullPointerException 如果值为 null
   */
  public static TokenTotalSemantics fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("Token 合计语义值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (TokenTotalSemantics semantics : values()) {
      if (semantics.value.equals(normalized)) {
        return semantics;
      }
    }
    throw new IllegalArgumentException("非法的 Token 合计语义值: '" + value + "'");
  }
}
