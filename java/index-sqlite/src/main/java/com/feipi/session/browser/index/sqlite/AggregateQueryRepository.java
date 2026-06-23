package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.index.sqlite.SqlUtils.WhereClauses;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.TitleFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 聚合查询只读仓库。
 *
 * <p>迁移 Python {@code queries.py} 和 {@code metrics.py} 中的项目统计、Dashboard 聚合、趋势分析、
 * token/工具/模型分布、效率指标等查询。所有 SQL 使用参数化绑定，用户输入仅作为参数。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>过滤值格式由 query-api 过滤器类型在 factory 完成校验。
 *   <li>排序字段合法性由 {@link com.feipi.session.browser.query.api.ProjectSortField} 枚举限定。
 *   <li>本类信任已验证的 typed filter，只负责 SQL 拼接和参数绑定。
 * </ul>
 */
public final class AggregateQueryRepository {

  /** 项目统计聚合 SELECT 子句，projectStats 和 listProjects 共享。 */
  private static final String PROJECT_STATS_SELECT =
      """
      SELECT
          project_key, project_name,
          COUNT(*) as total_sessions,
          SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
          SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
          SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
          MIN(started_at) as first_seen,
          MAX(ended_at) as last_seen,
          COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
          COALESCE(SUM(output_tokens), 0) as total_output_tokens,
          COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
          COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
          COALESCE(SUM(total_tokens), 0) as total_tokens,
          COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
          COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
          COALESCE(SUM(user_message_count), 0) as total_user_messages,
          COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
      FROM sessions\
      """;

  /** Top-N 项目聚合基础 SELECT，topProjectsByTokens 和 topProjectsByTools 共享。 */
  private static final String TOP_PROJECTS_BASE =
      """
      SELECT
          project_key, project_name,
          COALESCE(SUM(total_tokens), 0) as total_tokens,
          COALESCE(SUM(tool_call_count), 0) as total_tools,
          COALESCE(SUM(failed_tool_count), 0) as failed_tools,
          COUNT(*) as session_count
      FROM sessions GROUP BY project_key\
      """;

  private final IndexConnection indexConnection;

  /**
   * 使用已有 {@link IndexConnection} 创建仓库。
   *
   * @param indexConnection 已初始化的 index 连接，schema 必须已就绪
   */
  public AggregateQueryRepository(IndexConnection indexConnection) {
    this.indexConnection = Objects.requireNonNull(indexConnection, "indexConnection 不得为 null");
  }

  // ── 项目查询 ──

  /**
   * 查询单个项目的聚合统计。
   *
   * <p>对应 Python {@code get_project_stats}。不存在的项目返回空统计。
   *
   * @param projectKey 项目键
   * @return 项目统计行
   * @throws SQLException 查询失败
   */
  public ProjectStatsRow projectStats(String projectKey) throws SQLException {
    Objects.requireNonNull(projectKey, "projectKey 不得为 null");
    String sql = PROJECT_STATS_SELECT + " WHERE project_key = ? GROUP BY project_key";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, projectKey);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return mapProjectStatsRow(rs);
        }
        return new ProjectStatsRow(projectKey, "", 0, 0, 0, 0, "", "", 0, 0, 0, 0, 0, 0, 0, 0, 0);
      }
    }
  }

  /**
   * 计数匹配搜索条件的项目数。
   *
   * <p>对应 Python {@code count_projects}。搜索匹配 project_name、project_key 或 cwd。
   *
   * @param filter 项目列表过滤器
   * @return 去重项目数
   * @throws SQLException 查询失败
   */
  public long countProjects(ProjectListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    WhereClauses clauses = buildProjectSearchClauses(filter.titleFilter());
    String sql = "SELECT COUNT(DISTINCT project_key) FROM sessions " + clauses.whereFragment();
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      SqlUtils.bindParams(ps, clauses.params(), 1);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
      }
    }
  }

  /**
   * 分页查询项目聚合列表。
   *
   * <p>对应 Python {@code list_projects}。排序字段由枚举白名单限定。
   *
   * @param filter 项目列表过滤器
   * @return 分页项目统计结果
   * @throws SQLException 查询失败
   */
  public PageResult<ProjectStatsRow> listProjects(ProjectListFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    WhereClauses clauses = buildProjectSearchClauses(filter.titleFilter());
    Sort sort = filter.sort();
    PageRequest page = filter.page();

    String orderExpr = projectSortToSql(sort);
    String sql =
        (PROJECT_STATS_SELECT + " %s GROUP BY project_key ORDER BY %s LIMIT ? OFFSET ?")
            .formatted(clauses.whereFragment(), orderExpr);

    try (ReadTransaction rt = indexConnection.readTransaction()) {
      long totalCount = countDistinctProjects(rt, clauses);
      List<ProjectStatsRow> rows = new ArrayList<>();
      try (PreparedStatement ps = rt.connection().prepareStatement(sql)) {
        int idx = SqlUtils.bindParams(ps, clauses.params(), 1);
        ps.setInt(idx, page.limit());
        ps.setInt(idx + 1, page.offset());
        try (ResultSet rs = ps.executeQuery()) {
          while (rs.next()) {
            rows.add(mapProjectStatsRow(rs));
          }
        }
      }
      return PageResult.ofOffset(rows, totalCount);
    }
  }

  // ── Dashboard 查询 ──

  /**
   * Dashboard 全局聚合统计。
   *
   * <p>对应 Python {@code get_dashboard_stats}。可选 agent 范围过滤。
   *
   * @param agentFilter agent 过滤器
   * @return Dashboard 聚合行
   * @throws SQLException 查询失败
   */
  public DashboardRow dashboardStats(AgentFilter agentFilter) throws SQLException {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    String agentClause = agentWhereClause(agentFilter);
    String sql =
        """
        SELECT
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_sessions,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_sessions,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_sessions,
            COUNT(DISTINCT project_key) as project_count,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools,
            COALESCE(SUM(user_message_count), 0) as total_user_messages,
            COALESCE(SUM(assistant_message_count), 0) as total_assistant_messages
        FROM sessions %s\
        """
            .formatted(agentClause);
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      bindAgentParam(ps, agentFilter, 1);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return new DashboardRow(
            rs.getLong("total_sessions"),
            rs.getLong("claude_sessions"),
            rs.getLong("codex_sessions"),
            rs.getLong("qoder_sessions"),
            rs.getLong("project_count"),
            rs.getLong("total_tokens"),
            rs.getLong("total_fresh_input_tokens"),
            rs.getLong("total_cache_read_tokens"),
            rs.getLong("total_cache_write_tokens"),
            rs.getLong("total_output_tokens"),
            rs.getLong("total_tool_calls"),
            rs.getLong("total_failed_tools"),
            rs.getLong("total_user_messages"),
            rs.getLong("total_assistant_messages"));
      }
    }
  }

  // ── 趋势查询 ──

  /**
   * 每日 token 和会话趋势数据。
   *
   * <p>对应 Python {@code get_trend_data}。按日历日分组，包含 per-agent 计数和 token 分布。 日期范围由 {@link
   * TrendFilter#days} 控制。空 {@code ended_at} 归入当天。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的趋势行列表
   * @throws SQLException 查询失败
   */
  public List<TrendDayRow> trendData(TrendFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    String agentAndClause = agentAndFragment(filter.agentFilter());
    String sql =
        """
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            SUM(CASE WHEN agent='claude_code' THEN 1 ELSE 0 END) as claude_count,
            SUM(CASE WHEN agent='codex' THEN 1 ELSE 0 END) as codex_count,
            SUM(CASE WHEN agent='qoder' THEN 1 ELSE 0 END) as qoder_count,
            COALESCE(SUM(CASE WHEN agent='claude_code' THEN total_tokens ELSE 0 END), 0)
                as claude_tokens,
            COALESCE(SUM(CASE WHEN agent='codex' THEN total_tokens ELSE 0 END), 0)
                as codex_tokens,
            COALESCE(SUM(CASE WHEN agent='qoder' THEN total_tokens ELSE 0 END), 0)
                as qoder_tokens,
            COALESCE(SUM(fresh_input_tokens), 0) as fresh_input_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
            COALESCE(SUM(cache_write_tokens), 0) as cache_write_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_tokens), 0) as total_tokens,
            COALESCE(SUM(tool_call_count), 0) as tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as failed_tools,
            COUNT(*) as total_count
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        %s
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
        ORDER BY day\
        """
            .formatted(agentAndClause);
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      int idx = 1;
      ps.setString(idx++, "-" + filter.days() + " days");
      idx = bindAgentParam(ps, filter.agentFilter(), idx);
      return readTrendDayRows(ps);
    }
  }

  /**
   * 每日 prompt 活动趋势数据。
   *
   * <p>对应 Python {@code get_prompt_activity_trend}。按日历日分组，包含 per-agent prompt 计数。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的活动趋势行列表
   * @throws SQLException 查询失败
   */
  public List<ActivityTrendRow> activityTrend(TrendFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    String agentAndClause = agentAndFragment(filter.agentFilter());
    String sql =
        """
        SELECT
            COALESCE(NULLIF(DATE(ended_at), ''), DATE('now')) as day,
            COALESCE(SUM(CASE WHEN agent='claude_code' THEN user_message_count ELSE 0 END), 0)
                as claude_prompts,
            COALESCE(SUM(CASE WHEN agent='codex' THEN user_message_count ELSE 0 END), 0)
                as codex_prompts,
            COALESCE(SUM(CASE WHEN agent='qoder' THEN user_message_count ELSE 0 END), 0)
                as qoder_prompts,
            COALESCE(SUM(user_message_count), 0) as total_prompts,
            COALESCE(SUM(assistant_message_count), 0) as assistant_turns,
            COALESCE(SUM(tool_call_count), 0) as tool_calls
        FROM sessions
        WHERE (ended_at >= date('now', ?) OR ended_at = '' OR ended_at IS NULL)
        %s
        GROUP BY COALESCE(NULLIF(DATE(ended_at), ''), DATE('now'))
        ORDER BY day\
        """
            .formatted(agentAndClause);
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      int idx = 1;
      ps.setString(idx++, "-" + filter.days() + " days");
      bindAgentParam(ps, filter.agentFilter(), idx);
      return readActivityTrendRows(ps);
    }
  }

  // ── Token/分布查询 ──

  /**
   * Token 分类统计。
   *
   * <p>对应 Python {@code get_token_breakdown}。全表 SUM 聚合，空表返回全零。
   *
   * @return token 分类统计
   * @throws SQLException 查询失败
   */
  public TokenBreakdownRow tokenBreakdown() throws SQLException {
    String sql =
        """
        SELECT
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write,
            COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
            COALESCE(SUM(failed_tool_count), 0) as total_failed_tools
        FROM sessions\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql);
        ResultSet rs = ps.executeQuery()) {
      rs.next();
      return new TokenBreakdownRow(
          rs.getLong("total_fresh_input"),
          rs.getLong("total_output"),
          rs.getLong("total_cache_read"),
          rs.getLong("total_cache_write"),
          rs.getLong("total_tool_calls"),
          rs.getLong("total_failed_tools"));
    }
  }

  /**
   * 模型分布：每个非空模型的会话计数。
   *
   * <p>对应 Python {@code get_model_distribution}。按计数降序排列。
   *
   * @return 模型名称到会话计数的有序映射
   * @throws SQLException 查询失败
   */
  public Map<String, Long> modelDistribution() throws SQLException {
    String sql =
        "SELECT model, COUNT(*) as cnt FROM sessions"
            + " WHERE model != '' GROUP BY model ORDER BY cnt DESC";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql);
        ResultSet rs = ps.executeQuery()) {
      Map<String, Long> result = new LinkedHashMap<>();
      while (rs.next()) {
        result.put(rs.getString("model"), rs.getLong("cnt"));
      }
      return result;
    }
  }

  /**
   * Agent 分布：每个 agent 的会话计数。
   *
   * <p>对应 Python {@code get_agent_distribution}。按计数降序排列。
   *
   * @return agent 标识到会话计数的有序映射
   * @throws SQLException 查询失败
   */
  public Map<String, Long> agentDistribution() throws SQLException {
    String sql = "SELECT agent, COUNT(*) as cnt FROM sessions GROUP BY agent ORDER BY cnt DESC";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql);
        ResultSet rs = ps.executeQuery()) {
      Map<String, Long> result = new LinkedHashMap<>();
      while (rs.next()) {
        result.put(rs.getString("agent"), rs.getLong("cnt"));
      }
      return result;
    }
  }

  // ── Top-N 查询 ──

  /**
   * 工具分布：工具调用数最高的会话。
   *
   * <p>对应 Python {@code get_tool_distribution}。返回 per-session 工具总数。
   *
   * @param limit 最大返回行数
   * @return 会话键到工具分布条目的有序映射
   * @throws SQLException 查询失败
   */
  public Map<String, ToolDistributionEntry> toolDistribution(int limit) throws SQLException {
    validateLimit(limit);
    String sql =
        """
        SELECT session_key, title, tool_call_count
        FROM sessions WHERE tool_call_count > 0
        ORDER BY tool_call_count DESC LIMIT ?\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      try (ResultSet rs = ps.executeQuery()) {
        Map<String, ToolDistributionEntry> result = new LinkedHashMap<>();
        while (rs.next()) {
          result.put(
              rs.getString("session_key"),
              new ToolDistributionEntry(rs.getString("title"), rs.getLong("tool_call_count")));
        }
        return result;
      }
    }
  }

  /**
   * 按 token 总量排行的项目。
   *
   * <p>对应 Python {@code get_top_projects_by_tokens}。
   *
   * @param limit 最大返回行数
   * @return 按 token 总量降序排列的项目行列表
   * @throws SQLException 查询失败
   */
  public List<TopProjectRow> topProjectsByTokens(int limit) throws SQLException {
    validateLimit(limit);
    String sql = TOP_PROJECTS_BASE + " ORDER BY total_tokens DESC LIMIT ?";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      return readTopProjectRows(ps);
    }
  }

  /**
   * 按工具调用总数排行的项目。
   *
   * <p>对应 Python {@code get_top_projects_by_tools}。
   *
   * @param limit 最大返回行数
   * @return 按工具调用数降序排列的项目行列表
   * @throws SQLException 查询失败
   */
  public List<TopProjectRow> topProjectsByTools(int limit) throws SQLException {
    validateLimit(limit);
    String sql = TOP_PROJECTS_BASE + " ORDER BY total_tools DESC LIMIT ?";
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      return readTopProjectRows(ps);
    }
  }

  /**
   * 时长最长的会话。
   *
   * <p>对应 Python {@code get_slowest_sessions}。只包含正时长会话。
   *
   * @param limit 最大返回行数
   * @return 按时长降序排列的会话行列表
   * @throws SQLException 查询失败
   */
  public List<TopSessionRow> topSlowestSessions(int limit) throws SQLException {
    validateLimit(limit);
    String sql =
        """
        SELECT session_key, title, agent, model, duration_seconds,
               failed_tool_count, tool_call_count, project_name
        FROM sessions WHERE duration_seconds > 0
        ORDER BY duration_seconds DESC LIMIT ?\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      return readTopSessionRows(ps);
    }
  }

  /**
   * 有失败工具调用的会话。
   *
   * <p>对应 Python {@code get_failed_tool_sessions}。只包含正失败计数会话。
   *
   * @param limit 最大返回行数
   * @return 按失败工具数降序排列的会话行列表
   * @throws SQLException 查询失败
   */
  public List<TopSessionRow> topFailedToolSessions(int limit) throws SQLException {
    validateLimit(limit);
    String sql =
        """
        SELECT session_key, title, agent, model, failed_tool_count,
               duration_seconds, tool_call_count, project_name
        FROM sessions WHERE failed_tool_count > 0
        ORDER BY failed_tool_count DESC LIMIT ?\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      return readTopSessionRows(ps);
    }
  }

  /**
   * 缓存命中率最高的会话。
   *
   * <p>对应 Python {@code get_high_cache_read_sessions}。只包含有缓存读取的会话。 缓存命中率由 SQL 计算：{@code 100 *
   * cache_read / (fresh_input + cache_read)}。
   *
   * @param limit 最大返回行数
   * @return 按缓存命中率降序排列的会话行列表
   * @throws SQLException 查询失败
   */
  public List<CacheHitSessionRow> topHighCacheReadSessions(int limit) throws SQLException {
    validateLimit(limit);
    String sql =
        """
        SELECT
            session_key, title, agent, model,
            cache_read_tokens, fresh_input_tokens, project_name,
            CASE
                WHEN fresh_input_tokens + cache_read_tokens > 0
                THEN ROUND(100.0 * cache_read_tokens
                    / (fresh_input_tokens + cache_read_tokens), 1)
                ELSE 0
            END as cache_hit_pct
        FROM sessions WHERE cache_read_tokens > 0
        ORDER BY cache_hit_pct DESC LIMIT ?\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setInt(1, limit);
      List<CacheHitSessionRow> rows = new ArrayList<>();
      try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
          rows.add(
              new CacheHitSessionRow(
                  rs.getString("session_key"),
                  rs.getString("title"),
                  rs.getString("agent"),
                  rs.getString("model"),
                  rs.getLong("cache_read_tokens"),
                  rs.getLong("fresh_input_tokens"),
                  rs.getString("project_name"),
                  rs.getDouble("cache_hit_pct")));
        }
      }
      return rows;
    }
  }

  // ── 衍生指标 ──

  /**
   * Dashboard 级聚合衍生指标。
   *
   * <p>对应 Python {@code compute_aggregate_metrics}。计算缓存复用率、输出率、每轮工具数和 token 消耗。
   *
   * @return 聚合衍生指标行
   * @throws SQLException 查询失败
   */
  public AggregateMetricsRow aggregateMetrics() throws SQLException {
    String sql =
        """
        SELECT
            COALESCE(SUM(fresh_input_tokens), 0) as total_fresh_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(cache_write_tokens), 0) as total_cache_write,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds
        FROM sessions\
        """;
    try (ReadTransaction rt = indexConnection.readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql);
        ResultSet rs = ps.executeQuery()) {
      rs.next();
      return AggregateMetricsRow.compute(
          rs.getLong("total_fresh_input"),
          rs.getLong("total_output"),
          rs.getLong("total_cache_read"),
          rs.getLong("total_cache_write"),
          rs.getLong("total_tools"),
          rs.getLong("total_rounds"));
    }
  }

  /**
   * Agent + model 分组效率指标。
   *
   * <p>对应 Python {@code compute_agent_efficiency}。P95 时长由 Java 端 nearest-rank 近似计算， 避免在 SQL
   * 中使用窗口函数。
   *
   * @return 按会话数降序排列的效率行列表
   * @throws SQLException 查询失败
   */
  public List<AgentEfficiencyRow> agentEfficiency() throws SQLException {
    String groupSql =
        """
        SELECT
            agent,
            COALESCE(model, 'unknown') as model,
            COUNT(*) as session_count,
            AVG(duration_seconds) as avg_duration,
            COALESCE(SUM(fresh_input_tokens + cache_read_tokens + cache_write_tokens), 0)
                as total_input_side,
            COALESCE(SUM(tool_call_count), 0) as total_tools,
            COALESCE(SUM(assistant_message_count), 0) as total_rounds,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(failed_tool_count), 0) as total_failed
        FROM sessions GROUP BY agent, model
        ORDER BY session_count DESC\
        """;

    // 单独查询正时长数据用于 P95 计算
    String durationSql =
        """
        SELECT agent, COALESCE(model, 'unknown') as model, duration_seconds
        FROM sessions WHERE duration_seconds > 0
        ORDER BY agent, model, duration_seconds\
        """;

    try (ReadTransaction rt = indexConnection.readTransaction()) {
      // 收集 per-group 时长数据
      Map<String, List<Double>> durations = new LinkedHashMap<>();
      try (PreparedStatement dps = rt.connection().prepareStatement(durationSql);
          ResultSet drs = dps.executeQuery()) {
        while (drs.next()) {
          String key = drs.getString("agent") + "|||" + drs.getString("model");
          durations.computeIfAbsent(key, k -> new ArrayList<>()).add(drs.getDouble(3));
        }
      }

      // 主查询
      List<AgentEfficiencyRow> result = new ArrayList<>();
      try (PreparedStatement ps = rt.connection().prepareStatement(groupSql);
          ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
          String agent = rs.getString("agent");
          String model = rs.getString("model");
          String key = agent + "|||" + model;
          long sessionCount = rs.getLong("session_count");
          double avgDuration = rs.getDouble("avg_duration");
          long totalInputSide = rs.getLong("total_input_side");
          long totalTools = rs.getLong("total_tools");
          long totalRounds = rs.getLong("total_rounds");
          long totalCacheRead = rs.getLong("total_cache_read");
          long totalFailed = rs.getLong("total_failed");

          double p95 = nearestRankP95(durations.getOrDefault(key, List.of()));

          result.add(
              new AgentEfficiencyRow(
                  agent,
                  model,
                  sessionCount,
                  Math.round(avgDuration * 10.0) / 10.0,
                  Math.round(p95 * 10.0) / 10.0,
                  totalInputSide,
                  sessionCount > 0
                      ? Math.round((double) totalTools / sessionCount * 10.0) / 10.0
                      : 0.0,
                  AggregateMetricsRow.safeDivRound(totalTools, totalRounds, 2),
                  AggregateMetricsRow.safeDivRound(totalCacheRead, totalInputSide, 4),
                  AggregateMetricsRow.safeDivRound(totalFailed, sessionCount, 4)));
        }
      }
      return result;
    }
  }

  // ── 内部辅助方法 ──

  /** 项目搜索 WHERE 子句构建。 */
  private static WhereClauses buildProjectSearchClauses(TitleFilter titleFilter) {
    if (titleFilter.isUnfiltered()) {
      return new WhereClauses("", List.of());
    }
    String pattern = "%" + titleFilter.keyword() + "%";
    String where =
        "WHERE (LOWER(project_name) LIKE LOWER(?) "
            + "OR LOWER(project_key) LIKE LOWER(?) "
            + "OR LOWER(cwd) LIKE LOWER(?))";
    return new WhereClauses(where, List.of(pattern, pattern, pattern));
  }

  /** 生成 Dashboard 查询的 WHERE 子句。空过滤返回空字符串。 */
  private static String agentWhereClause(AgentFilter agentFilter) {
    if (agentFilter.isUnfiltered()) {
      return "";
    }
    return "WHERE agent = ?";
  }

  /** 生成趋势查询的 AND 追加片段。空过滤返回空字符串。 */
  private static String agentAndFragment(AgentFilter agentFilter) {
    if (agentFilter.isUnfiltered()) {
      return "";
    }
    return "AND agent = ?";
  }

  /** 绑定 agent 参数，返回下一个参数索引。 */
  private static int bindAgentParam(PreparedStatement ps, AgentFilter agentFilter, int index)
      throws SQLException {
    if (!agentFilter.isUnfiltered()) {
      ps.setString(index, agentFilter.agent());
      return index + 1;
    }
    return index;
  }

  /** 将项目排序转为 SQL ORDER BY 片段。LAST_ACTIVE 映射为 last_seen。 */
  private static String projectSortToSql(Sort sort) {
    // ProjectSortField.LAST_ACTIVE 的 sortKey 是 "last_active"，但 SQL 聚合别名是 "last_seen"
    if ("last_active".equals(sort.sortKey())) {
      return "last_seen " + sort.order().name();
    }
    return sort.toSqlFragment();
  }

  /** 统计去重项目数。 */
  private static long countDistinctProjects(ReadTransaction rt, WhereClauses clauses)
      throws SQLException {
    String sql = "SELECT COUNT(DISTINCT project_key) FROM sessions " + clauses.whereFragment();
    try (PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      SqlUtils.bindParams(ps, clauses.params(), 1);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
      }
    }
  }

  /** 映射 ProjectStatsRow（单项目和列表共用）。 */
  private static ProjectStatsRow mapProjectStatsRow(ResultSet rs) throws SQLException {
    return new ProjectStatsRow(
        rs.getString("project_key"),
        rs.getString("project_name"),
        rs.getLong("total_sessions"),
        rs.getLong("claude_sessions"),
        rs.getLong("codex_sessions"),
        rs.getLong("qoder_sessions"),
        SqlUtils.nullToEmpty(rs.getString("first_seen")),
        SqlUtils.nullToEmpty(rs.getString("last_seen")),
        rs.getLong("total_fresh_input_tokens"),
        rs.getLong("total_output_tokens"),
        rs.getLong("total_cache_read_tokens"),
        rs.getLong("total_cache_write_tokens"),
        rs.getLong("total_tokens"),
        rs.getLong("total_tool_calls"),
        rs.getLong("total_failed_tools"),
        rs.getLong("total_user_messages"),
        rs.getLong("total_assistant_messages"));
  }

  /** 读取趋势日数据行。 */
  private static List<TrendDayRow> readTrendDayRows(PreparedStatement ps) throws SQLException {
    List<TrendDayRow> rows = new ArrayList<>();
    try (ResultSet rs = ps.executeQuery()) {
      while (rs.next()) {
        rows.add(
            new TrendDayRow(
                rs.getString("day"),
                rs.getLong("claude_count"),
                rs.getLong("codex_count"),
                rs.getLong("qoder_count"),
                rs.getLong("claude_tokens"),
                rs.getLong("codex_tokens"),
                rs.getLong("qoder_tokens"),
                rs.getLong("fresh_input_tokens"),
                rs.getLong("cache_read_tokens"),
                rs.getLong("cache_write_tokens"),
                rs.getLong("output_tokens"),
                rs.getLong("total_tokens"),
                rs.getLong("tool_calls"),
                rs.getLong("failed_tools"),
                rs.getLong("total_count")));
      }
    }
    return rows;
  }

  /** 读取活动趋势行。 */
  private static List<ActivityTrendRow> readActivityTrendRows(PreparedStatement ps)
      throws SQLException {
    List<ActivityTrendRow> rows = new ArrayList<>();
    try (ResultSet rs = ps.executeQuery()) {
      while (rs.next()) {
        rows.add(
            new ActivityTrendRow(
                rs.getString("day"),
                rs.getLong("claude_prompts"),
                rs.getLong("codex_prompts"),
                rs.getLong("qoder_prompts"),
                rs.getLong("total_prompts"),
                rs.getLong("assistant_turns"),
                rs.getLong("tool_calls")));
      }
    }
    return rows;
  }

  /** 读取 Top-N 项目行。 */
  private static List<TopProjectRow> readTopProjectRows(PreparedStatement ps) throws SQLException {
    List<TopProjectRow> rows = new ArrayList<>();
    try (ResultSet rs = ps.executeQuery()) {
      while (rs.next()) {
        rows.add(
            new TopProjectRow(
                rs.getString("project_key"),
                rs.getString("project_name"),
                rs.getLong("total_tokens"),
                rs.getLong("total_tools"),
                rs.getLong("failed_tools"),
                rs.getLong("session_count")));
      }
    }
    return rows;
  }

  /** 读取 Top-N 会话行。 */
  private static List<TopSessionRow> readTopSessionRows(PreparedStatement ps) throws SQLException {
    List<TopSessionRow> rows = new ArrayList<>();
    try (ResultSet rs = ps.executeQuery()) {
      while (rs.next()) {
        rows.add(
            new TopSessionRow(
                rs.getString("session_key"),
                rs.getString("title"),
                rs.getString("agent"),
                rs.getString("model"),
                rs.getString("project_name"),
                rs.getDouble("duration_seconds"),
                rs.getLong("failed_tool_count"),
                rs.getLong("tool_call_count")));
      }
    }
    return rows;
  }

  /** Nearest-rank P95 近似。与 Python 实现一致。 */
  private static double nearestRankP95(List<Double> values) {
    if (values.isEmpty()) {
      return 0;
    }
    List<Double> sorted = new ArrayList<>(values);
    sorted.sort(Double::compare);
    int idx = (int) (0.95 * (sorted.size() - 1));
    return sorted.get(idx);
  }

  /** 校验 limit 参数为正整数。 */
  private static void validateLimit(int limit) {
    if (limit < 1) {
      throw new IllegalArgumentException("limit 必须为正; got " + limit);
    }
  }

  /**
   * 工具分布条目。
   *
   * @param title 会话标题
   * @param toolCallCount 工具调用数
   */
  public record ToolDistributionEntry(String title, long toolCallCount) {}
}
