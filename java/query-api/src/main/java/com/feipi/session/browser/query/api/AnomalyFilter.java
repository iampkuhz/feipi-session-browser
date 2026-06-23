package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 异常类型过滤器。
 *
 * <p>按异常类别过滤诊断结果。null 表示不过滤（匹配所有异常类型）。
 *
 * <p>校验在 factory 完成，repository 信任已验证的值。
 */
public final class AnomalyFilter {

  /** 不过滤任何异常类型的实例。 */
  public static final AnomalyFilter NONE = new AnomalyFilter(null);

  private final AnomalyType type;

  private AnomalyFilter(AnomalyType type) {
    this.type = type;
  }

  /**
   * 创建异常类型过滤器。
   *
   * @param type 异常类型，null 表示不过滤
   * @return 新的异常过滤器
   */
  public static AnomalyFilter of(AnomalyType type) {
    return new AnomalyFilter(type);
  }

  /**
   * 是否为空过滤。
   *
   * @return 当 type 为 null 时返回 true
   */
  public boolean isUnfiltered() {
    return type == null;
  }

  /**
   * 获取异常类型。
   *
   * @return 异常类型，null 表示不过滤
   */
  public AnomalyType type() {
    return type;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof AnomalyFilter other)) return false;
    return Objects.equals(type, other.type);
  }

  @Override
  public int hashCode() {
    return Objects.hashCode(type);
  }

  @Override
  public String toString() {
    return isUnfiltered() ? "AnomalyFilter[*]" : "AnomalyFilter[" + type.getValue() + "]";
  }
}
