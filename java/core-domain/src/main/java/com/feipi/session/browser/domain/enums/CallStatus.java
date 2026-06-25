package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 调用状态枚举。
 *
 * <p>标识一次 LLM 调用的最终执行结果状态。 用于 token 归因、错误统计和会话质量分析。
 */
@DomainModel
@RequiredArgsConstructor
public enum CallStatus {
  /** 调用成功完成。 */
  OK("ok"),

  /** 调用执行出错。 */
  ERROR("error");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析调用状态。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的调用状态枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知状态
   * @throws NullPointerException 如果值为 null
   */
  public static CallStatus fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("调用状态值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (CallStatus status : values()) {
      if (status.value.equals(normalized)) {
        return status;
      }
    }
    throw new IllegalArgumentException("非法的调用状态值: '" + value + "'。允许值: ok, error");
  }
}
