package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 排序方向枚举。
 *
 * <p>对应 SQL {@code ORDER BY} 的 {@code ASC} / {@code DESC}。用于所有 typed query 的排序声明。
 */
@RequiredArgsConstructor
public enum SortOrder {
  /** 升序排列。 */
  ASC("asc"),

  /** 降序排列。 */
  DESC("desc");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析排序方向。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的排序方向枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知方向
   * @throws NullPointerException 如果值为 null
   */
  public static SortOrder fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("排序方向值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (SortOrder order : values()) {
      if (order.value.equals(normalized)) {
        return order;
      }
    }
    throw new IllegalArgumentException("非法的排序方向值: '" + value + "'。允许值: asc, desc");
  }

  /**
   * 将字符串解析为排序方向。
   *
   * <p>不区分大小写，支持 {@code asc}/{@code desc} 两种输入。
   *
   * @param value 排序方向字符串
   * @return 对应的排序方向枚举
   * @throws IllegalArgumentException 当值无法识别时
   */
  public static SortOrder fromString(String value) {
    if ("asc".equalsIgnoreCase(value)) {
      return ASC;
    }
    if ("desc".equalsIgnoreCase(value)) {
      return DESC;
    }
    throw new IllegalArgumentException("无法识别的排序方向: " + value + "; 合法值为 asc 或 desc");
  }
}
