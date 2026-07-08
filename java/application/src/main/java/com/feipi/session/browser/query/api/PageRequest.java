package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 分页请求。
 *
 * <p>支持 offset 分页和 cursor 分页两种模式。offset 分页使用 {@link #offset()} 和 {@link #limit()}； cursor 分页使用
 * {@link #cursor()} 和 {@link #limit()}。两种模式互斥，cursor 模式优先。
 *
 * <p>默认值：offset=0，limit=50。上限：limit 不超过 500。
 *
 * <p>校验在 factory 完成：
 *
 * <ul>
 *   <li>{@code limit} 必须在 [1, 500] 范围内。
 *   <li>{@code offset} 必须非负。
 *   <li>{@code cursor} 为空字符串时等同于未设置。
 * </ul>
 *
 * <p>下游 repository 信任已验证的 {@code PageRequest} 不变量，不重复解析数值范围。
 */
public final class PageRequest {

  /** 每页默认大小。 */
  public static final int DEFAULT_LIMIT = 50;

  /** 每页最大大小。 */
  public static final int MAX_LIMIT = 500;

  /** 默认 offset 分页请求：第一页，50 条。 */
  public static final PageRequest DEFAULT = new PageRequest(0, DEFAULT_LIMIT, "");

  private final int offset;
  private final int limit;
  private final String cursor;

  private PageRequest(int offset, int limit, String cursor) {
    this.offset = offset;
    this.limit = limit;
    this.cursor = cursor;
  }

  /**
   * 创建 offset 分页请求。
   *
   * @param offset 起始偏移量，必须非负
   * @param limit 每页大小，必须在 [1, 500] 范围内
   * @return 新的分页请求
   * @throws IllegalArgumentException 当参数超出合法范围时
   */
  public static PageRequest ofOffset(int offset, int limit) {
    if (offset < 0) {
      throw new IllegalArgumentException("offset 必须非负; got " + offset);
    }
    validateLimit(limit);
    return new PageRequest(offset, limit, "");
  }

  /**
   * 创建 cursor 分页请求。
   *
   * @param cursor 分页游标，空字符串表示首页
   * @param limit 每页大小，必须在 [1, 500] 范围内
   * @return 新的分页请求
   * @throws IllegalArgumentException 当 limit 超出范围时
   * @throws NullPointerException 当 cursor 为 null 时
   */
  public static PageRequest ofCursor(String cursor, int limit) {
    Objects.requireNonNull(cursor, "cursor 不得为 null");
    validateLimit(limit);
    return new PageRequest(0, limit, cursor);
  }

  /**
   * 创建仅指定 limit 的分页请求，offset 默认为 0。
   *
   * @param limit 每页大小
   * @return 新的分页请求
   * @throws IllegalArgumentException 当 limit 超出范围时
   */
  public static PageRequest ofLimit(int limit) {
    return ofOffset(0, limit);
  }

  private static void validateLimit(int limit) {
    if (limit < 1 || limit > MAX_LIMIT) {
      throw new IllegalArgumentException("limit 必须在 [1, " + MAX_LIMIT + "] 范围内; got " + limit);
    }
  }

  /**
   * 获取起始偏移量。
   *
   * <p>cursor 模式下始终为 0。
   *
   * @return 非负偏移量
   */
  public int offset() {
    return offset;
  }

  /**
   * 获取每页大小。
   *
   * @return 正整数 limit
   */
  public int limit() {
    return limit;
  }

  /**
   * 获取分页游标。
   *
   * <p>空字符串表示未设置（首页请求）。offset 模式下始终为空字符串。
   *
   * @return 游标字符串，永不为 null
   */
  public String cursor() {
    return cursor;
  }

  /**
   * 是否为 cursor 分页模式。
   *
   * @return 当 cursor 非空时返回 true
   */
  public boolean isCursorMode() {
    return !cursor.isEmpty();
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof PageRequest other)) return false;
    return offset == other.offset && limit == other.limit && cursor.equals(other.cursor);
  }

  @Override
  public int hashCode() {
    return Objects.hash(offset, limit, cursor);
  }

  @Override
  public String toString() {
    if (isCursorMode()) {
      return "PageRequest[cursor=" + cursor + ", limit=" + limit + "]";
    }
    return "PageRequest[offset=" + offset + ", limit=" + limit + "]";
  }
}
