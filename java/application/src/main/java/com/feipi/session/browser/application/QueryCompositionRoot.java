package com.feipi.session.browser.application;

import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;

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
  private final IndexConnection indexConnection;

  /**
   * 创建 composition root。
   *
   * @param indexConnection 已初始化的 index 连接
   * @param schemaVersion 当前 schema 版本号
   * @param cache 可选缓存，null 时不缓存
   */
  public QueryCompositionRoot(
      IndexConnection indexConnection, SchemaVersion schemaVersion, QueryCache cache) {
    if (indexConnection == null) {
      throw new IllegalArgumentException("indexConnection 不得为 null");
    }
    if (schemaVersion == null) {
      throw new IllegalArgumentException("schemaVersion 不得为 null");
    }

    this.schemaVersion = schemaVersion.version();
    this.cache = cache;
    this.indexConnection = indexConnection;

    SessionQueryRepository sessionRepo = new SessionQueryRepository(indexConnection);
    AggregateQueryRepository aggregateRepo = new AggregateQueryRepository(indexConnection);
    SessionDetailRepository detailRepo = new SessionDetailRepository(sessionRepo);

    this.sessionList = new SessionListUseCase(sessionRepo, cache, this.schemaVersion);
    this.projectList = new ProjectListUseCase(aggregateRepo, cache, this.schemaVersion);
    this.dashboard = new DashboardUseCase(aggregateRepo, cache, this.schemaVersion);
    this.sessionDetail = new SessionDetailUseCase(detailRepo, this.schemaVersion);
    this.diagnostics = new DiagnosticsUseCase();
  }

  /**
   * 创建无缓存的 composition root。
   *
   * @param indexConnection 已初始化的 index 连接
   * @param schemaVersion 当前 schema 版本号
   */
  public QueryCompositionRoot(IndexConnection indexConnection, SchemaVersion schemaVersion) {
    this(indexConnection, schemaVersion, null);
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

  /**
   * 获取底层 index 连接。
   *
   * <p>供 Web 层创建共享连接的仓库实例（如 {@code SessionDetailRepository}）。
   *
   * @return index 连接实例
   */
  public IndexConnection indexConnection() {
    return indexConnection;
  }
}
