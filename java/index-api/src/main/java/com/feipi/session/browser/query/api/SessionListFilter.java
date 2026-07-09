package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 会话列表复合过滤器。
 *
 * <p>组合 agent、project、model、title、failure status 等单一维度过滤器， 加上排序和分页规范，形成完整的会话列表查询请求。
 *
 * <p>所有字段不可变，在 factory 完成校验。下游 repository 信任已验证的不变量， 不重复解析字符串或校验数值范围。
 *
 * <p>默认值：
 *
 * <ul>
 *   <li>排序：{@link Sort#DEFAULT_SESSION}（按 ended_at DESC）
 *   <li>分页：{@link PageRequest#DEFAULT}（offset=0, limit=50）
 *   <li>所有过滤器默认不过滤
 * </ul>
 */
public final class SessionListFilter {

  private final AgentFilter agentFilter;
  private final ProjectFilter projectFilter;
  private final ModelFilter modelFilter;
  private final TitleFilter titleFilter;
  private final FailureStatus failureStatus;
  private final Sort sort;
  private final PageRequest page;

  private SessionListFilter(
      AgentFilter agentFilter,
      ProjectFilter projectFilter,
      ModelFilter modelFilter,
      TitleFilter titleFilter,
      FailureStatus failureStatus,
      Sort sort,
      PageRequest page) {
    this.agentFilter = agentFilter;
    this.projectFilter = projectFilter;
    this.modelFilter = modelFilter;
    this.titleFilter = titleFilter;
    this.failureStatus = failureStatus;
    this.sort = sort;
    this.page = page;
  }

  /**
   * 创建全默认值的会话列表过滤器。
   *
   * @return 不过滤任何条件的默认实例
   */
  public static SessionListFilter defaults() {
    return new SessionListFilter(
        AgentFilter.NONE,
        ProjectFilter.NONE,
        ModelFilter.NONE,
        TitleFilter.NONE,
        FailureStatus.ALL,
        Sort.DEFAULT_SESSION,
        PageRequest.DEFAULT);
  }

  /**
   * 基于当前过滤器创建新的实例，替换 agent 过滤器。
   *
   * @param agentFilter 新的 agent 过滤器
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withAgent(AgentFilter agentFilter) {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换项目过滤器。
   *
   * @param projectFilter 新的项目过滤器
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withProject(ProjectFilter projectFilter) {
    Objects.requireNonNull(projectFilter, "projectFilter 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换模型过滤器。
   *
   * @param modelFilter 新的模型过滤器
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withModel(ModelFilter modelFilter) {
    Objects.requireNonNull(modelFilter, "modelFilter 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换标题过滤器。
   *
   * @param titleFilter 新的标题过滤器
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withTitle(TitleFilter titleFilter) {
    Objects.requireNonNull(titleFilter, "titleFilter 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换失败状态过滤器。
   *
   * @param failureStatus 新的失败状态
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withFailureStatus(FailureStatus failureStatus) {
    Objects.requireNonNull(failureStatus, "failureStatus 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换排序规范。
   *
   * @param sort 新的排序规范
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withSort(Sort sort) {
    Objects.requireNonNull(sort, "sort 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换分页请求。
   *
   * @param page 新的分页请求
   * @return 新的会话列表过滤器
   */
  public SessionListFilter withPage(PageRequest page) {
    Objects.requireNonNull(page, "page 不得为 null");
    return new SessionListFilter(
        agentFilter, projectFilter, modelFilter, titleFilter, failureStatus, sort, page);
  }

  /**
   * 获取 agent 过滤器。
   *
   * @return agent 过滤器
   */
  public AgentFilter agentFilter() {
    return agentFilter;
  }

  /**
   * 获取项目过滤器。
   *
   * @return 项目过滤器
   */
  public ProjectFilter projectFilter() {
    return projectFilter;
  }

  /**
   * 获取模型过滤器。
   *
   * @return 模型过滤器
   */
  public ModelFilter modelFilter() {
    return modelFilter;
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
   * 获取失败状态过滤器。
   *
   * @return 失败状态
   */
  public FailureStatus failureStatus() {
    return failureStatus;
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
    return "SessionListFilter["
        + agentFilter
        + ", "
        + projectFilter
        + ", "
        + modelFilter
        + ", "
        + titleFilter
        + ", "
        + failureStatus
        + ", "
        + sort
        + ", "
        + page
        + "]";
  }
}
