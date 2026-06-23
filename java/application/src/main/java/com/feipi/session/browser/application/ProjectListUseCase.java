package com.feipi.session.browser.application;

import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;
import java.sql.SQLException;
import java.util.Objects;

/**
 * 项目列表查询 use case。
 *
 * <p>组合 {@link AggregateQueryRepository} 的项目相关查询：list/count/stats。 支持可选缓存加速重复查询。
 *
 * <p>校验放置：过滤参数由 {@link ProjectListFilter} 在入口验证，本 use case 信任已验证的 typed filter。
 */
public final class ProjectListUseCase {

  private final AggregateQueryRepository repository;
  private final QueryCache cache;
  private final int schemaVersion;

  /**
   * 创建项目列表 use case。
   *
   * @param repository 聚合查询仓库
   * @param cache 可选缓存，null 时不缓存
   * @param schemaVersion 当前 schema 版本号
   */
  public ProjectListUseCase(
      AggregateQueryRepository repository, QueryCache cache, int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
    this.cache = cache;
    this.schemaVersion = schemaVersion;
  }

  /**
   * 分页查询项目列表。
   *
   * @param filter 项目列表过滤器
   * @return 分页项目统计结果
   * @throws SQLException 查询失败
   */
  public PageResult<ProjectStatsRow> list(ProjectListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");

    if (cache != null) {
      int paramsHash = filterHash("list", filter);
      return cache.getOrLoad(
          "projectList",
          paramsHash,
          schemaVersion,
          () -> {
            try {
              return repository.listProjects(filter);
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.listProjects(filter);
  }

  /**
   * 计数匹配搜索条件的项目数。
   *
   * @param filter 项目列表过滤器
   * @return 去重项目数
   * @throws SQLException 查询失败
   */
  public long count(ProjectListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    return repository.countProjects(filter);
  }

  /**
   * 查询单个项目的聚合统计。
   *
   * @param projectKey 项目键
   * @return 项目统计行
   * @throws SQLException 查询失败
   */
  public ProjectStatsRow stats(String projectKey) throws SQLException {
    Objects.requireNonNull(projectKey, "projectKey 不得为 null");
    return repository.projectStats(projectKey);
  }

  /** 计算过滤器哈希，用于缓存键。 */
  private static int filterHash(String op, ProjectListFilter filter) {
    return Objects.hash(op, filter.titleFilter(), filter.sort(), filter.page());
  }
}
