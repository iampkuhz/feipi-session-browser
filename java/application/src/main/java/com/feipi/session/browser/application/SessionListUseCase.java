package com.feipi.session.browser.application;

import com.feipi.session.browser.application.diagnostics.AnomalyDetector;
import com.feipi.session.browser.index.api.query.ProjectOption;
import com.feipi.session.browser.index.api.query.SessionListAggregate;
import com.feipi.session.browser.index.api.query.SessionListSummary;
import com.feipi.session.browser.index.api.query.SessionQueryPort;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Objects;

/**
 * 会话列表查询 use case。
 *
 * <p>组合 {@link SessionQueryPort} 的 list/count/aggregate 操作，附加异常检测结果。 支持可选缓存加速重复查询。
 *
 * <p>校验放置：过滤参数由 {@link SessionListFilter} 在入口验证，本 use case 信任已验证的 typed filter。
 */
public final class SessionListUseCase {

  private static final String FILTER_NULL_MESSAGE = "filter 不得为 null";

  private final SessionQueryPort repository;
  private final QueryCache cache;
  private final int schemaVersion;

  /**
   * 创建会话列表 use case。
   *
   * @param repository 会话查询仓库
   * @param cache 可选缓存，null 时不缓存
   * @param schemaVersion 当前 schema 版本号
   */
  public SessionListUseCase(SessionQueryPort repository, QueryCache cache, int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
    this.cache = cache;
    this.schemaVersion = schemaVersion;
  }

  /**
   * 分页查询会话列表，附加异常检测。
   *
   * @param filter 会话列表过滤器
   * @return 分页结果，包含异常摘要
   */
  public AnnotatedPageResult listWithAnomalies(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);

    PageResult<SessionRecord> page;
    if (cache != null) {
      int paramsHash = filterHash("list", filter);
      page =
          cache.getOrLoad(
              "sessionList", paramsHash, schemaVersion, () -> repository.listSessions(filter));
    } else {
      page = repository.listSessions(filter);
    }

    List<SessionAnomalySummary> anomalies = AnomalyDetector.detectAll(page.items());
    return new AnnotatedPageResult(page, anomalies);
  }

  /**
   * 过滤后会话总数。
   *
   * @param filter 会话列表过滤器
   * @return 匹配会话数
   */
  public long count(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);
    return repository.countSessions(filter);
  }

  /**
   * 过滤后会话列表聚合。
   *
   * @param filter 会话列表过滤器
   * @return 聚合结果
   */
  public SessionListAggregate aggregate(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);
    return repository.listAggregate(filter);
  }

  /**
   * 过滤后会话列表完整聚合。
   *
   * @param filter 会话列表过滤器
   * @return 完整聚合结果，包含 token 四段和 failed tool
   */
  public SessionListSummary summary(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);
    return repository.listSummary(filter);
  }

  /**
   * 查询会话列表 model 筛选候选项。
   *
   * @param filter 会话列表过滤器
   * @return model 候选值
   */
  public List<String> modelOptions(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);
    return repository.listModelOptions(filter);
  }

  /**
   * 查询会话列表 project 筛选候选项。
   *
   * @param filter 会话列表过滤器
   * @return project 候选值
   */
  public List<ProjectOption> projectOptions(SessionListFilter filter) {
    Objects.requireNonNull(filter, FILTER_NULL_MESSAGE);
    return repository.listProjectOptions(filter);
  }

  /** 计算过滤器哈希，用于缓存键。 */
  private static int filterHash(String op, SessionListFilter filter) {
    return Objects.hash(
        op,
        filter.agentFilter(),
        filter.projectFilter(),
        filter.modelFilter(),
        filter.titleFilter(),
        filter.failureStatus(),
        filter.sort(),
        filter.page());
  }

  /**
   * 附带异常摘要的分页结果。
   *
   * @param page 原始分页结果
   * @param anomalies 每个会话的异常摘要，顺序与 page.items() 一致
   */
  public record AnnotatedPageResult(
      /* 原始分页结果。 */
      @NotNull PageResult<SessionRecord> page,

      /* 每个会话的异常摘要，顺序与 page.items() 一致。 */
      @NotNull List<SessionAnomalySummary> anomalies) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AnnotatedPageResult {
      ValidationSupport.validateCanonicalConstructor(AnnotatedPageResult.class, page, anomalies);
      if (anomalies.size() != page.size()) {
        throw new IllegalArgumentException(
            "anomalies 大小必须与 page 一致; anomalies=" + anomalies.size() + ", page=" + page.size());
      }
    }
  }
}
