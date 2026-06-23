package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 源单元方向枚举。
 *
 * <p>标识源单元属于调用的请求侧还是响应侧。与 Python 端 {@code _DIRECTION_VALUES} 集合对应， 仅允许 {@code request} 和 {@code
 * response} 两个合法值。
 */
@DomainModel
@RequiredArgsConstructor
public enum SourceUnitDirection {
  /** 请求侧，包含用户输入和工具结果。 */
  REQUEST("request"),

  /** 响应侧，包含助手输出和工具调用。 */
  RESPONSE("response");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static SourceUnitDirection fromValue(String value) {
    for (SourceUnitDirection direction : values()) {
      if (direction.value.equals(value)) {
        return direction;
      }
    }
    throw new IllegalArgumentException("invalid source unit direction: " + value);
  }
}
