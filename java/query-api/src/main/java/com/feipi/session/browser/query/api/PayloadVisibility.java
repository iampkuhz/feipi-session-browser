package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * payload 可见性策略枚举。
 *
 * <p>控制会话详情 API 返回的 payload 内容是否包含敏感字段。 单一 owner 管理全部可见性规则，避免多处分散判断。
 *
 * <ul>
 *   <li>{@link #STANDARD}：敏感字段默认隐藏，只返回摘要级 payload。
 *   <li>{@link #FULL}：展开全部 payload 内容，包括请求和响应正文。
 * </ul>
 */
@RequiredArgsConstructor
public enum PayloadVisibility {

  /** 标准可见性：敏感字段默认隐藏。 */
  STANDARD("standard"),

  /** 完整可见性：展开全部 payload 正文。 */
  FULL("full");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析 payload 可见性策略。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的 payload 可见性枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知策略
   * @throws NullPointerException 如果值为 null
   */
  public static PayloadVisibility fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("Payload 可见性值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (PayloadVisibility visibility : values()) {
      if (visibility.value.equals(normalized)) {
        return visibility;
      }
    }
    throw new IllegalArgumentException("非法的 payload 可见性值: '" + value + "'。允许值: standard, full");
  }
}
