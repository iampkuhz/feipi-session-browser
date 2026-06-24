package com.feipi.session.browser.web.page;

import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.ModelFilter;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.TitleFilter;
import java.util.Map;
import java.util.Set;

/**
 * HTTP 查询参数解析。
 *
 * <p>将 Javalin {@code ctx.queryParamMap()} 的原始字符串映射转换为 typed query-api 过滤器对象。 校验在 HTTP adapter
 * 入口一次性完成，下游 use case 信任已验证的 typed filter。
 *
 * <p>对应 Python presenters 中的 {@code parse_*_query_params} 函数族。
 */
public final class QueryParams {

  private static final Set<Integer> VALID_PAGE_SIZES = Set.of(25, 50, 100);

  /** Sessions 页面 UI sort key 到 query-api 排序字段的映射。 */
  private static final Map<String, String> SESSION_SORT_MAP =
      Map.ofEntries(
          Map.entry("ended-at", "ended_at"),
          Map.entry("updated", "ended_at"),
          Map.entry("created", "started_at"),
          Map.entry("duration", "duration_seconds"),
          Map.entry("process-time", "model_execution_seconds"),
          Map.entry("tokens", "total_tokens"),
          Map.entry("total-tokens", "total_tokens"),
          Map.entry("rounds", "assistant_message_count"),
          Map.entry("tools", "tool_call_count"),
          Map.entry("subagents", "subagent_instance_count"),
          Map.entry("failure", "failed_tool_count"));

  /** Projects 页面 UI sort key 到 query-api ProjectSortField 的映射。 */
  private static final Map<String, String> PROJECT_SORT_MAP =
      Map.ofEntries(
          Map.entry("sessions", "total_sessions"),
          Map.entry("tokens", "total_tokens"),
          Map.entry("tools", "total_tool_calls"),
          Map.entry("failed", "total_failed_tools"),
          Map.entry("first_seen", "first_seen"),
          Map.entry("last_active", "last_active"));

  private QueryParams() {}

  /**
   * 从 Javalin query param map 解析 page 参数。
   *
   * @param params query param map
   * @return 1-based 页码，最小为 1
   */
  public static int parsePage(Map<String, String> params) {
    try {
      int page = Integer.parseInt(params.getOrDefault("page", "1"));
      return Math.max(page, 1);
    } catch (NumberFormatException e) {
      return 1;
    }
  }

  /**
   * 从 Javalin query param map 解析 page_size 参数。
   *
   * <p>只接受 25/50/100 三个合法值，其余回退到 25。
   *
   * @param params query param map
   * @return 合法的页面大小
   */
  public static int parsePageSize(Map<String, String> params) {
    String raw = params.getOrDefault("page_size", "25").trim().toLowerCase();
    try {
      int size = Integer.parseInt(raw);
      if (VALID_PAGE_SIZES.contains(size)) {
        return size;
      }
    } catch (NumberFormatException ignored) {
      // 回退到默认值
    }
    return 25;
  }

  /**
   * 解析会话列表查询参数，构建 typed SessionListFilter。
   *
   * @param params Javalin 扁平 query param map
   * @return 已验证的会话列表过滤器
   */
  public static SessionListFilter parseSessionListFilter(Map<String, String> params) {
    SessionListFilter filter = SessionListFilter.defaults();

    String agent = params.getOrDefault("agent", "").trim();
    if (!agent.isEmpty()) {
      filter = filter.withAgent(AgentFilter.of(agent));
    }

    String model = params.getOrDefault("model", "").trim();
    if (!model.isEmpty()) {
      filter = filter.withModel(ModelFilter.of(model));
    }

    String project = params.getOrDefault("project", "").trim();
    if (!project.isEmpty()) {
      filter = filter.withProject(ProjectFilter.of(project));
    }

    String q = params.getOrDefault("q", "").trim();
    if (!q.isEmpty()) {
      filter = filter.withTitle(TitleFilter.of(q));
    }

    String status = params.getOrDefault("status", "").trim().toLowerCase();
    if ("failed".equals(status)) {
      filter = filter.withFailureStatus(FailureStatus.FAILED_ONLY);
    } else if ("no-failures".equals(status)) {
      filter = filter.withFailureStatus(FailureStatus.SUCCESS_ONLY);
    }

    String rawSort = params.getOrDefault("sort", "").trim().toLowerCase();
    String rawDir = params.getOrDefault("dir", "desc").trim().toLowerCase();
    String dir = ("asc".equals(rawDir)) ? "asc" : "desc";
    if (!rawSort.isEmpty()) {
      String dbField = SESSION_SORT_MAP.getOrDefault(rawSort, "ended_at");
      filter = filter.withSort(Sort.ofSession(dbField, dir));
    }

    int page = parsePage(params);
    int pageSize = parsePageSize(params);
    int offset = (page - 1) * pageSize;
    filter = filter.withPage(PageRequest.ofOffset(offset, pageSize));

    return filter;
  }

  /**
   * 解析项目列表查询参数，构建 typed ProjectListFilter。
   *
   * @param params Javalin 扁平 query param map
   * @return 已验证的项目列表过滤器
   */
  public static ProjectListFilter parseProjectListFilter(Map<String, String> params) {
    ProjectListFilter filter = ProjectListFilter.defaults();

    String q = params.getOrDefault("q", "").trim();
    if (!q.isEmpty()) {
      filter = filter.withTitle(TitleFilter.of(q));
    }

    String rawSort = params.getOrDefault("sort", "last_active").trim().toLowerCase();
    String rawDir = params.getOrDefault("dir", "desc").trim().toLowerCase();
    String dir = ("asc".equals(rawDir)) ? "asc" : "desc";
    String sortKey = PROJECT_SORT_MAP.getOrDefault(rawSort, "last_active");
    filter = filter.withSort(Sort.ofProject(sortKey, dir));

    int page = parsePage(params);
    int pageSize = parsePageSize(params);
    int offset = (page - 1) * pageSize;
    filter = filter.withPage(PageRequest.ofOffset(offset, pageSize));

    return filter;
  }

  /**
   * 返回 UI 使用的 sort key echo（模板需要回显当前排序字段）。
   *
   * <p>Python 中 template 使用 'updated' 代替 'ended-at'，此处做等价映射。
   *
   * @param params Javalin 扁平 query param map
   * @return UI sort key
   */
  public static String uiSortKey(Map<String, String> params) {
    String raw = params.getOrDefault("sort", "").trim().toLowerCase();
    if ("ended-at".equals(raw)) {
      return "updated";
    }
    return raw.isEmpty() ? "ended-at" : raw;
  }
}
