package com.feipi.session.browser.query.api;

import java.util.List;
import java.util.Objects;

/**
 * 分页结果。
 *
 * <p>封装查询返回的条目列表和分页元数据。不可变值对象，{@code items} 在创建时做防御性拷贝。
 *
 * <p>{@code totalCount} 为符合过滤条件的总条目数，可能为 -1 表示总数未计算（cursor 分页场景）。 {@code nextCursor} 为空字符串表示没有更多数据。
 *
 * @param <T> 结果条目类型
 * @param items 当前页的条目列表，不可变
 * @param totalCount 总条目数，-1 表示未计算
 * @param nextCursor 下一页游标，空字符串表示已到末尾
 */
public record PageResult<T>(List<T> items, long totalCount, String nextCursor) {

  /**
   * 紧凑构造器，验证不变量并防御性拷贝。
   *
   * @throws NullPointerException 当 items 或 nextCursor 为 null 时
   * @throws IllegalArgumentException 当 totalCount 小于 -1 时
   */
  public PageResult {
    Objects.requireNonNull(items, "items 不得为 null");
    Objects.requireNonNull(nextCursor, "nextCursor 不得为 null");
    if (totalCount < -1) {
      throw new IllegalArgumentException("totalCount 必须 >= -1; got " + totalCount);
    }
    items = List.copyOf(items);
  }

  /**
   * 创建不带 cursor 的分页结果。
   *
   * @param items 条目列表
   * @param totalCount 总条目数
   * @param <T> 条目类型
   * @return 新的分页结果
   */
  public static <T> PageResult<T> ofOffset(List<T> items, long totalCount) {
    return new PageResult<>(items, totalCount, "");
  }

  /**
   * 创建带 cursor 的分页结果。
   *
   * @param items 条目列表
   * @param totalCount 总条目数，-1 表示未计算
   * @param nextCursor 下一页游标
   * @param <T> 条目类型
   * @return 新的分页结果
   */
  public static <T> PageResult<T> ofCursor(List<T> items, long totalCount, String nextCursor) {
    return new PageResult<>(items, totalCount, nextCursor);
  }

  /**
   * 是否有更多数据。
   *
   * @return 当 nextCursor 非空时返回 true
   */
  public boolean hasMore() {
    return !nextCursor.isEmpty();
  }

  /**
   * 当前页条目数。
   *
   * @return 条目数量
   */
  public int size() {
    return items.size();
  }

  /**
   * 是否为空结果。
   *
   * @return 当 items 为空时返回 true
   */
  public boolean isEmpty() {
    return items.isEmpty();
  }
}
