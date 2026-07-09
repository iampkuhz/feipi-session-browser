package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 项目列表复合过滤器。
 *
 * <p>组合标题关键字过滤器，加上排序和分页规范，形成完整的项目列表查询请求。
 *
 * <p>默认值：
 *
 * <ul>
 *   <li>排序：{@link Sort#DEFAULT_PROJECT}（按最近活跃时间降序）
 *   <li>分页：{@link PageRequest#DEFAULT}（offset=0, limit=50）
 * </ul>
 */
public final class ProjectListFilter {

  private final TitleFilter titleFilter;
  private final Sort sort;
  private final PageRequest page;

  private ProjectListFilter(TitleFilter titleFilter, Sort sort, PageRequest page) {
    this.titleFilter = titleFilter;
    this.sort = sort;
    this.page = page;
  }

  /**
   * 创建全默认值的项目列表过滤器。
   *
   * @return 不过滤任何条件的默认实例
   */
  public static ProjectListFilter defaults() {
    return new ProjectListFilter(TitleFilter.NONE, Sort.DEFAULT_PROJECT, PageRequest.DEFAULT);
  }

  /**
   * 基于当前过滤器创建新的实例，替换标题过滤器。
   *
   * @param titleFilter 新的标题过滤器
   * @return 新的项目列表过滤器
   */
  public ProjectListFilter withTitle(TitleFilter titleFilter) {
    Objects.requireNonNull(titleFilter, "titleFilter 不得为 null");
    return new ProjectListFilter(titleFilter, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换排序规范。
   *
   * <p>排序字段必须使用 {@link ProjectSortField} 对应的列。
   *
   * @param sort 新的排序规范
   * @return 新的项目列表过滤器
   */
  public ProjectListFilter withSort(Sort sort) {
    Objects.requireNonNull(sort, "sort 不得为 null");
    return new ProjectListFilter(titleFilter, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换分页请求。
   *
   * @param page 新的分页请求
   * @return 新的项目列表过滤器
   */
  public ProjectListFilter withPage(PageRequest page) {
    Objects.requireNonNull(page, "page 不得为 null");
    return new ProjectListFilter(titleFilter, sort, page);
  }

  /**
   * 获取标题过滤器。
   *
   * @return 标题过滤器
   */
  public TitleFilter titleFilter() {
    return titleFilter;
  }

  /**
   * 获取排序规范。
   *
   * @return 排序规范
   */
  public Sort sort() {
    return sort;
  }

  /**
   * 获取分页请求。
   *
   * @return 分页请求
   */
  public PageRequest page() {
    return page;
  }

  @Override
  public String toString() {
    return "ProjectListFilter[" + titleFilter + ", " + sort + ", " + page + "]";
  }
}
