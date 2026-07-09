package com.feipi.session.browser.application;

import com.feipi.session.browser.application.sessiondetail.NormalizedArtifactReader;
import com.feipi.session.browser.index.api.query.AggregateQueryPort;
import com.feipi.session.browser.index.api.query.SessionDetailPort;
import com.feipi.session.browser.index.api.query.SessionQueryPort;
import java.util.Objects;

/**
 * 查询 composition root。
 *
 * <p>集中装配所有 use case，提供统一的查询入口。构造器注入，不引入 DI framework。
 *
 * <p>缓存策略：共享一个有界 {@link QueryCache}，scan/mutation 后调用 {@link #invalidateCache()} 失效。
 */
public final class QueryCompositionRoot {

  private final SessionListUseCase sessionList;
  private final ProjectListUseCase projectList;
  private final DashboardUseCase dashboard;
  private final SessionDetailUseCase sessionDetail;
  private final DiagnosticsUseCase diagnostics;
  private final QueryCache cache;
  private final int schemaVersion;

  /**
   * 创建 composition root。
   *
   * @param sessionRepository 会话查询端口
   * @param aggregateRepository 聚合查询端口
   * @param detailRepository 会话详情查询端口
   * @param artifactReader 归一化制品读取器
   * @param schemaVersion 当前 schema 版本号
   * @param cache 可选缓存，null 时不缓存
   */
  public QueryCompositionRoot(
      SessionQueryPort sessionRepository,
      AggregateQueryPort aggregateRepository,
      SessionDetailPort detailRepository,
      NormalizedArtifactReader artifactReader,
      int schemaVersion,
      QueryCache cache) {
    this.schemaVersion = schemaVersion;
    this.cache = cache;

    this.sessionList =
        new SessionListUseCase(
            Objects.requireNonNull(sessionRepository, "sessionRepository 不得为 null"),
            cache,
            schemaVersion);
    this.projectList =
        new ProjectListUseCase(
            Objects.requireNonNull(aggregateRepository, "aggregateRepository 不得为 null"),
            cache,
            schemaVersion);
    this.dashboard = new DashboardUseCase(aggregateRepository, cache, schemaVersion);
    this.sessionDetail =
        new SessionDetailUseCase(
            Objects.requireNonNull(detailRepository, "detailRepository 不得为 null"),
            Objects.requireNonNull(artifactReader, "artifactReader 不得为 null"),
            schemaVersion);
    this.diagnostics = new DiagnosticsUseCase();
  }

  /**
   * 创建无缓存的 composition root。
   *
   * @param sessionRepository 会话查询端口
   * @param aggregateRepository 聚合查询端口
   * @param detailRepository 会话详情查询端口
   * @param artifactReader 归一化制品读取器
   * @param schemaVersion 当前 schema 版本号
   */
  public QueryCompositionRoot(
      SessionQueryPort sessionRepository,
      AggregateQueryPort aggregateRepository,
      SessionDetailPort detailRepository,
      NormalizedArtifactReader artifactReader,
      int schemaVersion) {
    this(
        sessionRepository,
        aggregateRepository,
        detailRepository,
        artifactReader,
        schemaVersion,
        null);
  }

  /** 获取会话列表 use case。 */
  public SessionListUseCase sessionList() {
    return sessionList;
  }

  /** 获取项目列表 use case。 */
  public ProjectListUseCase projectList() {
    return projectList;
  }

  /** 获取仪表板聚合查询用例。 */
  public DashboardUseCase dashboard() {
    return dashboard;
  }

  /** 获取会话详情 use case。 */
  public SessionDetailUseCase sessionDetail() {
    return sessionDetail;
  }

  /** 获取诊断 use case。 */
  public DiagnosticsUseCase diagnostics() {
    return diagnostics;
  }

  /**
   * 失效所有缓存。
   *
   * <p>scan 或 mutation 后调用，使所有缓存条目失效。无缓存时为空操作。
   */
  public void invalidateCache() {
    if (cache != null) {
      cache.invalidateAll();
    }
  }

  /**
   * 获取当前缓存实例。
   *
   * @return 缓存实例，无缓存时返回 null
   */
  public QueryCache cache() {
    return cache;
  }

  /**
   * 获取当前 schema 版本号。
   *
   * @return 正整数版本号
   */
  public int schemaVersion() {
    return schemaVersion;
  }
}
