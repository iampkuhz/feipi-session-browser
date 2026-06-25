package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 排序规范，封装排序字段标识和方向。
 *
 * <p>不可变值对象。内部存储排序字段的数据库列名或聚合标识，由 factory 方法在创建时校验。 下游 repository 信任其不变量，不再重复解析。
 *
 * <p>支持两种排序上下文：
 *
 * <ul>
 *   <li>会话排序：通过 {@link #ofSession} 工厂方法，字段受 {@link SessionSortField} 枚举限定。
 *   <li>项目排序：通过 {@link #ofProject} 工厂方法，字段受 {@link ProjectSortField} 枚举限定。
 * </ul>
 */
public final class Sort {

  /** 会话列表默认排序：按末事件时间降序。 */
  public static final Sort DEFAULT_SESSION = ofSession(SessionSortField.ENDED_AT, SortOrder.DESC);

  /** 项目列表默认排序：按最近活跃时间降序。 */
  public static final Sort DEFAULT_PROJECT =
      ofProject(ProjectSortField.LAST_ACTIVE, SortOrder.DESC);

  private final String sortKey;
  private final SortOrder order;

  private Sort(String sortKey, SortOrder order) {
    this.sortKey = sortKey;
    this.order = order;
  }

  /**
   * 创建会话排序规范。
   *
   * @param field 排序字段
   * @param order 排序方向
   * @return 新的排序规范
   * @throws NullPointerException 当参数为 null 时
   */
  public static Sort ofSession(SessionSortField field, SortOrder order) {
    Objects.requireNonNull(field, "排序字段不得为 null");
    Objects.requireNonNull(order, "排序方向不得为 null");
    return new Sort(field.getColumnName(), order);
  }

  /**
   * 创建项目排序规范。
   *
   * @param field 排序字段
   * @param order 排序方向
   * @return 新的排序规范
   * @throws NullPointerException 当参数为 null 时
   */
  public static Sort ofProject(ProjectSortField field, SortOrder order) {
    Objects.requireNonNull(field, "排序字段不得为 null");
    Objects.requireNonNull(order, "排序方向不得为 null");
    return new Sort(field.getSortKey(), order);
  }

  /**
   * 从字符串创建会话排序规范。
   *
   * @param field 排序字段名
   * @param order 排序方向字符串（asc/desc）
   * @return 新的排序规范
   * @throws IllegalArgumentException 当参数非法时
   */
  public static Sort ofSession(String field, String order) {
    return new Sort(SessionSortField.fromString(field).getColumnName(), SortOrder.fromValue(order));
  }

  /**
   * 从字符串创建项目排序规范。
   *
   * @param field 排序字段名
   * @param order 排序方向字符串（asc/desc）
   * @return 新的排序规范
   * @throws IllegalArgumentException 当参数非法时
   */
  public static Sort ofProject(String field, String order) {
    return new Sort(ProjectSortField.fromString(field).getSortKey(), SortOrder.fromValue(order));
  }

  /**
   * 获取排序字段标识。
   *
   * <p>会话排序为数据库列名，项目排序为聚合标识。
   *
   * @return 排序字段标识
   */
  public String sortKey() {
    return sortKey;
  }

  /**
   * 获取排序方向。
   *
   * @return 排序方向
   */
  public SortOrder order() {
    return order;
  }

  /**
   * 生成 SQL ORDER BY 子句片段。
   *
   * @return 形如 {@code ended_at DESC} 的 SQL 片段
   */
  public String toSqlFragment() {
    return sortKey + " " + order.name();
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof Sort other)) return false;
    return sortKey.equals(other.sortKey) && order == other.order;
  }

  @Override
  public int hashCode() {
    return Objects.hash(sortKey, order);
  }

  @Override
  public String toString() {
    return "Sort[" + sortKey + " " + order + "]";
  }
}
