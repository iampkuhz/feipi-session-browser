package com.feipi.session.browser.common.validation;

import java.util.Objects;

/** 通用参数与不变量校验工具。 */
public final class ParamChecks {

  private ParamChecks() {}

  /**
   * 校验对象不为 {@code null}。
   *
   * @param value 待校验对象
   * @param fieldName 字段名称
   * @param <T> 对象类型
   * @return 原始对象
   * @throws NullPointerException 当对象为 {@code null} 时
   */
  public static <T> T nonNull(T value, String fieldName) {
    return Objects.requireNonNull(value, fieldName + " 不得为 null");
  }

  /**
   * 校验参数不为 {@code null}，失败时抛出 {@link IllegalArgumentException}。
   *
   * @param value 待校验对象
   * @param fieldName 字段名称
   * @param <T> 对象类型
   * @return 原始对象
   * @throws IllegalArgumentException 当对象为 {@code null} 时
   */
  public static <T> T required(T value, String fieldName) {
    if (value == null) {
      throw new IllegalArgumentException(fieldName + " 不得为 null");
    }
    return value;
  }

  /**
   * 校验字符串不为 {@code null} 且不为空白。
   *
   * @param value 待校验字符串
   * @param fieldName 字段名称
   * @return 原始字符串
   * @throws IllegalArgumentException 当字符串为 {@code null} 或空白时
   */
  public static String nonBlank(String value, String fieldName) {
    if (value == null || value.isBlank()) {
      throw new IllegalArgumentException(fieldName + " 不得为空");
    }
    return value;
  }

  /**
   * 校验字符串不为 {@code null} 且长度大于零。
   *
   * @param value 待校验字符串
   * @param fieldName 字段名称
   * @return 原始字符串
   * @throws NullPointerException 当字符串为 {@code null} 时
   * @throws IllegalArgumentException 当字符串为空字符串时
   */
  public static String nonEmpty(String value, String fieldName) {
    Objects.requireNonNull(value, fieldName + " 不得为 null");
    if (value.isEmpty()) {
      throw new IllegalArgumentException(fieldName + " 不得为空字符串");
    }
    return value;
  }

  /**
   * 校验整数非负。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值为负数时
   */
  public static int nonNegative(int value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
    return value;
  }

  /**
   * 校验长整数非负。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值为负数时
   */
  public static long nonNegative(long value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
    return value;
  }

  /**
   * 校验浮点数非负。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值为负数时
   */
  public static double nonNegative(double value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
    return value;
  }

  /**
   * 校验整数为正数。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值小于 1 时
   */
  public static int positive(int value, String fieldName) {
    if (value < 1) {
      throw new IllegalArgumentException(fieldName + " 必须为正; got " + value);
    }
    return value;
  }

  /**
   * 校验长整数为正数。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值小于 1 时
   */
  public static long positive(long value, String fieldName) {
    if (value < 1) {
      throw new IllegalArgumentException(fieldName + " 必须为正; got " + value);
    }
    return value;
  }

  /**
   * 校验整数不小于指定下限。
   *
   * @param value 字段值
   * @param minInclusive 最小允许值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值小于下限时
   */
  public static int atLeast(int value, int minInclusive, String fieldName) {
    if (value < minInclusive) {
      throw new IllegalArgumentException(fieldName + " 必须 >= " + minInclusive + "; got " + value);
    }
    return value;
  }

  /**
   * 校验长整数不小于指定下限。
   *
   * @param value 字段值
   * @param minInclusive 最小允许值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值小于下限时
   */
  public static long atLeast(long value, long minInclusive, String fieldName) {
    if (value < minInclusive) {
      throw new IllegalArgumentException(fieldName + " 必须 >= " + minInclusive + "; got " + value);
    }
    return value;
  }

  /**
   * 校验整数落在闭区间内。
   *
   * @param value 字段值
   * @param minInclusive 最小允许值
   * @param maxInclusive 最大允许值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值不在闭区间内时
   */
  public static int inRange(int value, int minInclusive, int maxInclusive, String fieldName) {
    if (value < minInclusive || value > maxInclusive) {
      throw new IllegalArgumentException(
          fieldName + " 必须在 [" + minInclusive + ", " + maxInclusive + "] 范围内; got " + value);
    }
    return value;
  }

  /**
   * 校验浮点数落在闭区间内。
   *
   * @param value 字段值
   * @param minInclusive 最小允许值
   * @param maxInclusive 最大允许值
   * @param fieldName 字段名称
   * @return 原始字段值
   * @throws IllegalArgumentException 当字段值不在闭区间内时
   */
  public static double inRange(
      double value, double minInclusive, double maxInclusive, String fieldName) {
    if (value < minInclusive || value > maxInclusive) {
      throw new IllegalArgumentException(
          fieldName + " 必须在 [" + minInclusive + ", " + maxInclusive + "] 范围内; got " + value);
    }
    return value;
  }
}
