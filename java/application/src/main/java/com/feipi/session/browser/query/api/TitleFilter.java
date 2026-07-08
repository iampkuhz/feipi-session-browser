package com.feipi.session.browser.query.api;

/**
 * 标题关键字过滤器。
 *
 * <p>按标题关键字模糊匹配会话或项目。空字符串表示不过滤。 使用 SQL {@code LIKE} 模式匹配，% 通配符在 repository 层添加。
 *
 * <p>校验在 factory 完成：值 trim 后存储，repository 信任已验证的值。
 */
public final class TitleFilter {

  /** 不过滤的实例。 */
  public static final TitleFilter NONE = new TitleFilter("");

  private final String keyword;

  private TitleFilter(String keyword) {
    this.keyword = keyword;
  }

  /**
   * 创建标题关键字过滤器。
   *
   * <p>输入值自动 trim。空字符串表示不过滤。
   *
   * @param keyword 标题关键字，空字符串或 null 表示不过滤
   * @return 新的标题过滤器
   */
  public static TitleFilter of(String keyword) {
    if (keyword == null) {
      return NONE;
    }
    return new TitleFilter(keyword.trim());
  }

  /**
   * 是否为空过滤。
   *
   * @return 当关键字为空字符串时返回 true
   */
  public boolean isUnfiltered() {
    return keyword.isEmpty();
  }

  /**
   * 获取关键字。
   *
   * @return 已 trim 的关键字，空字符串表示不过滤
   */
  public String keyword() {
    return keyword;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof TitleFilter other)) return false;
    return keyword.equals(other.keyword);
  }

  @Override
  public int hashCode() {
    return keyword.hashCode();
  }

  @Override
  public String toString() {
    return isUnfiltered() ? "TitleFilter[*]" : "TitleFilter[" + keyword + "]";
  }
}
