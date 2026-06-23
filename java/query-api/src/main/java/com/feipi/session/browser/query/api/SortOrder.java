package com.feipi.session.browser.query.api;

/**
 * 排序方向枚举。
 *
 * <p>对应 SQL {@code ORDER BY} 的 {@code ASC} / {@code DESC}。用于所有 typed query 的排序声明。
 */
public enum SortOrder {
  /** 升序排列。 */
  ASC,

  /** 降序排列。 */
  DESC;

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
