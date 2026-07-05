package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.SessionListAggregate;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.web.model.PaginationModel;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Sessions 列表页面路由处理器。
 *
 * <p>处理 {@code GET /sessions} 请求：解析查询参数，调用 use case，组装模板上下文，渲染 HTML 响应。 路由只负责 HTTP input 解析和 output
 * 渲染，不包含业务逻辑。
 *
 * <p>校验放置：查询参数在 {@link QueryParams} 中校验一次，use case 信任 typed filter，模板信任已验证的上下文值。
 */
public final class SessionsPage {

  private static final Logger LOG = LoggerFactory.getLogger(SessionsPage.class);

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Sessions 页面处理器。
   *
   * @param queryRoot 查询 composition root
   * @param templates Pebble 模板环境
   */
  public SessionsPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET /sessions 请求。
   *
   * @param ctx Javalin 请求上下文
   */
  public void handle(Context ctx) {
    Map<String, String> params = flatQueryParams(ctx);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);

    try {
      SessionListUseCase useCase = queryRoot.sessionList();

      // 查询总数（用于分页计算）
      long totalCount = useCase.count(filter);

      // 查询聚合指标
      SessionListAggregate aggregate = useCase.aggregate(filter);

      // 查询分页会话列表（附带异常检测）
      SessionListUseCase.AnnotatedPageResult result = useCase.listWithAnomalies(filter);
      PageResult<SessionRow> page = result.page();
      List<SessionAnomalySummary> anomalies = result.anomalies();

      // 计算分页模型
      int currentPage = QueryParams.parsePage(params);
      int pageSize = QueryParams.parsePageSize(params);
      PaginationModel pagination = PaginationModel.of(currentPage, pageSize, (int) totalCount);

      // 组装模板上下文
      Map<String, Object> context = new HashMap<>();
      context.put("sessions", page.items());
      context.put("anomalies", anomalies);
      context.put("total_count", totalCount);
      context.put("sessions_aggregate", aggregate);
      context.putAll(pagination.toTemplateContext());

      // 过滤器回显值
      context.put(
          "filter_agent", QueryParams.normalizeSessionAgent(params.getOrDefault("agent", "")));
      context.put("filter_model", params.getOrDefault("model", ""));
      context.put("filter_project", params.getOrDefault("project", ""));
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("filter_status", params.getOrDefault("status", ""));
      String sortBy = QueryParams.uiSortKey(params);
      context.put("sort_by", sortBy);
      String sortDir = normalizeSortDir(params.getOrDefault("dir", "desc"));
      context.put("sort_dir", sortDir);
      context.put("sort_urls", buildSortUrls(params, sortBy, sortDir, pageSize));
      context.put("active_page", "sessions");

      String html = templates.render("sessions.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Sessions 页面查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(renderError(ctx, "查询会话列表失败"));
    }
  }

  private static String normalizeSortDir(String value) {
    return "asc".equalsIgnoreCase(value) ? "asc" : "desc";
  }

  private static Map<String, String> buildSortUrls(
      Map<String, String> params, String currentSort, String currentDir, int pageSize) {
    String[] keys = {
      "tokens",
      "rounds",
      "tools",
      "subagents",
      "duration",
      "process-time",
      "failure",
      "created",
      "updated"
    };
    Map<String, String> urls = new HashMap<>();
    for (String key : keys) {
      String nextDir = key.equals(currentSort) && "desc".equals(currentDir) ? "asc" : "desc";
      urls.put(key, buildSessionsUrl(params, key, nextDir, pageSize));
    }
    return urls;
  }

  private static String buildSessionsUrl(
      Map<String, String> params, String sortKey, String sortDir, int pageSize) {
    Map<String, String> clean = new LinkedHashMap<>();
    putIfNotEmpty(clean, "q", params.getOrDefault("q", ""));
    putIfNotEmpty(
        clean, "agent", QueryParams.normalizeSessionAgent(params.getOrDefault("agent", "")));
    putIfNotEmpty(clean, "status", params.getOrDefault("status", ""));
    putIfNotEmpty(clean, "model", params.getOrDefault("model", ""));
    putIfNotEmpty(clean, "project", params.getOrDefault("project", ""));
    clean.put("sort", sortKey);
    clean.put("dir", normalizeSortDir(sortDir));
    if (pageSize != 25) {
      clean.put("page_size", Integer.toString(pageSize));
    }

    StringBuilder query = new StringBuilder();
    for (Map.Entry<String, String> entry : clean.entrySet()) {
      if (query.length() > 0) {
        query.append('&');
      }
      query.append(encode(entry.getKey())).append('=').append(encode(entry.getValue()));
    }
    return "/sessions" + (query.length() == 0 ? "" : "?" + query);
  }

  private static void putIfNotEmpty(Map<String, String> target, String key, String value) {
    String trimmed = value == null ? "" : value.trim();
    if (!trimmed.isEmpty()) {
      target.put(key, trimmed);
    }
  }

  private static String encode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
  }

  private String renderError(Context ctx, String message) {
    Map<String, Object> errCtx = Map.of("error", message, "active_page", "sessions");
    return templates.render("error.html", errCtx);
  }

  /**
   * 将 Javalin 多值 query param map 展平为单值 map。
   *
   * <p>每个参数取第一个值，空值忽略。
   *
   * @param ctx Javalin 请求上下文
   * @return 扁平参数 map
   */
  static Map<String, String> flatQueryParams(Context ctx) {
    Map<String, String> result = new HashMap<>();
    for (Map.Entry<String, List<String>> entry : ctx.queryParamMap().entrySet()) {
      List<String> values = entry.getValue();
      if (values != null && !values.isEmpty()) {
        result.put(entry.getKey(), values.get(0));
      }
    }
    return result;
  }
}
