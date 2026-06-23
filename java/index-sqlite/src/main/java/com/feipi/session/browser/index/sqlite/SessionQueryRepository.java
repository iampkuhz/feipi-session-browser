package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.ModelFilter;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.TitleFilter;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * 会话只读查询仓库。
 *
 * <p>迁移 Python {@code queries.py} 中 session list、search、count 和 lookup 四个查询。 所有 SQL
 * 使用参数化绑定，用户输入仅作为参数，不拼接 SQL。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>过滤值格式由 {@link SessionListFilter} 及其子过滤器在 factory 完成校验。
 *   <li>排序字段合法性由 {@link com.feipi.session.browser.query.api.SessionSortField} 枚举限定。
 *   <li>本类信任已验证的 typed filter，只负责 SQL 拼接和参数绑定。
 * </ul>
 *
 * <p>读事务短生命周期：每个方法在 try-with-resources 中使用 {@link ReadTransaction}， 查询完成即释放。
 */
public final class SessionQueryRepository {

  private final IndexConnection indexConnection;

  /**
   * 使用已有 {@link IndexConnection} 创建仓库。
   *
   * @param indexConnection 已初始化的 index 连接，schema 必须已就绪
   */
  public SessionQueryRepository(IndexConnection indexConnection) {
    this.indexConnection = Objects.requireNonNull(indexConnection, "indexConnection 不得为 null");
  }

  /**
   * 按主键查找单个会话。
   *
   * <p>对应 Python {@code get_session}。详情路由使用此查询。
   *
   * @param sessionKey 会话主键，格式 {@code agent:session_id}
   * @return 匹配的行，不存在时返回 empty
   * @throws SQLException 查询失败
   */
  public Optional<SessionRow> getSession(String sessionKey) throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    String sql =
        "SELECT " + SessionResultSetMapper.ALL_COLUMNS + " FROM sessions WHERE session_key = ?";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, sessionKey);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return Optional.of(SessionResultSetMapper.mapRow(rs));
        }
        return Optional.empty();
      }
    }
  }

  /**
   * 过滤、排序、分页查询会话列表。
   *
   * <p>对应 Python {@code list_sessions}。排序字段来自枚举白名单，无 SQL 注入风险。
   *
   * @param filter 会话列表复合过滤器
   * @return 分页结果，包含会话行和总数
   * @throws SQLException 查询失败
   */
  public PageResult<SessionRow> listSessions(SessionListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");

    FilterClauses clauses = buildFilterClauses(filter);
    Sort sort = filter.sort();
    PageRequest page = filter.page();

    // 列表查询：SELECT + WHERE + ORDER BY + LIMIT + OFFSET
    String listSql =
        "SELECT "
            + SessionResultSetMapper.ALL_COLUMNS
            + " FROM sessions "
            + clauses.whereFragment()
            + " ORDER BY "
            + sort.toSqlFragment()
            + " LIMIT ? OFFSET ?";

    try (ReadTransaction rt = indexConnection.readTransaction()) {
      // 先查总数
      long totalCount = executeCountQuery(rt.connection(), clauses);

      // 再查列表
      List<SessionRow> rows = new ArrayList<>();
      try (PreparedStatement ps = rt.connection().prepareStatement(listSql)) {
        int paramIndex = bindFilterParams(ps, clauses, 1);
        ps.setInt(paramIndex, page.limit());
        ps.setInt(paramIndex + 1, page.offset());
        try (ResultSet rs = ps.executeQuery()) {
          while (rs.next()) {
            rows.add(SessionResultSetMapper.mapRow(rs));
          }
        }
      }

      return PageResult.ofOffset(rows, totalCount);
    }
  }

  /**
   * 过滤后会话总数。
   *
   * <p>对应 Python {@code count_sessions}。与 {@link #listSessions} 共享 WHERE 构建逻辑。
   *
   * @param filter 会话列表复合过滤器
   * @return 匹配会话数
   * @throws SQLException 查询失败
   */
  public long countSessions(SessionListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    FilterClauses clauses = buildFilterClauses(filter);
    try (ReadTransaction rt = indexConnection.readTransaction()) {
      return executeCountQuery(rt.connection(), clauses);
    }
  }

  /**
   * 过滤后会话列表聚合总量。
   *
   * <p>对应 Python {@code get_sessions_list_aggregate}。返回会话数、去重项目数和 token 总量。
   *
   * @param filter 会话列表复合过滤器
   * @return 聚合结果
   * @throws SQLException 查询失败
   */
  public SessionListAggregate listAggregate(SessionListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    FilterClauses clauses = buildFilterClauses(filter);
    String sql =
        "SELECT COUNT(*) AS session_count,"
            + " COUNT(DISTINCT project_key) AS project_count,"
            + " COALESCE(SUM(total_tokens), 0) AS total_tokens"
            + " FROM sessions "
            + clauses.whereFragment();

    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      bindFilterParams(ps, clauses, 1);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return new SessionListAggregate(
            rs.getLong("session_count"), rs.getLong("project_count"), rs.getLong("total_tokens"));
      }
    }
  }

  /**
   * 构建过滤 WHERE 子句和参数列表。
   *
   * <p>list、count、aggregate 三个查询共享同一过滤逻辑。 所有用户输入作为参数绑定，不拼接 SQL。
   */
  private static FilterClauses buildFilterClauses(SessionListFilter filter) {
    List<String> clauses = new ArrayList<>();
    List<Object> params = new ArrayList<>();

    // agent 过滤
    AgentFilter agentFilter = filter.agentFilter();
    if (!agentFilter.isUnfiltered()) {
      clauses.add("agent = ?");
      params.add(agentFilter.agent());
    }

    // 项目过滤
    ProjectFilter projectFilter = filter.projectFilter();
    if (!projectFilter.isUnfiltered()) {
      clauses.add("project_key = ?");
      params.add(projectFilter.projectKey());
    }

    // 模型过滤
    ModelFilter modelFilter = filter.modelFilter();
    if (!modelFilter.isUnfiltered()) {
      clauses.add("model = ?");
      params.add(modelFilter.model());
    }

    // 标题搜索：同时匹配 title 和 session_id，与 Python 行为一致
    TitleFilter titleFilter = filter.titleFilter();
    if (!titleFilter.isUnfiltered()) {
      clauses.add("(LOWER(title) LIKE LOWER(?) OR LOWER(session_id) LIKE LOWER(?))");
      String pattern = "%" + titleFilter.keyword() + "%";
      params.add(pattern);
      params.add(pattern);
    }

    // 失败状态过滤
    FailureStatus failureStatus = filter.failureStatus();
    if (failureStatus == FailureStatus.FAILED_ONLY) {
      clauses.add("failed_tool_count > 0");
    } else if (failureStatus == FailureStatus.SUCCESS_ONLY) {
      clauses.add("failed_tool_count = 0");
    }

    String whereFragment = clauses.isEmpty() ? "" : "WHERE " + String.join(" AND ", clauses);
    return new FilterClauses(whereFragment, List.copyOf(params));
  }

  /** 执行 COUNT(*) 查询。 */
  private static long executeCountQuery(Connection conn, FilterClauses clauses)
      throws SQLException {
    String sql = "SELECT COUNT(*) FROM sessions " + clauses.whereFragment();
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
      bindFilterParams(ps, clauses, 1);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
      }
    }
  }

  /** 绑定过滤参数到 PreparedStatement，返回下一个参数索引。 */
  private static int bindFilterParams(PreparedStatement ps, FilterClauses clauses, int startIndex)
      throws SQLException {
    int index = startIndex;
    for (Object param : clauses.params()) {
      if (param instanceof String s) {
        ps.setString(index, s);
      } else if (param instanceof Long l) {
        ps.setLong(index, l);
      } else if (param instanceof Integer i) {
        ps.setInt(index, i);
      }
      index++;
    }
    return index;
  }

  /**
   * 过滤 WHERE 子句片段和参数列表。
   *
   * <p>不可变值对象。{@code whereFragment} 为空字符串或 {@code WHERE ...} 形式。 {@code params} 为对应的绑定参数，顺序与 {@code
   * ?} 占位符一致。
   */
  private record FilterClauses(String whereFragment, List<Object> params) {}
}
