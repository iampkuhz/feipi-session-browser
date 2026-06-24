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
import java.sql.SQLException;
import java.util.HashMap;
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
      context.put("page", pagination.page());
      context.put("current_page", pagination.page());
      context.put("page_size", pageSize);
      context.put("total_pages", pagination.totalPages());
      context.put("page_start", pagination.pageStart());
      context.put("page_end", pagination.pageEnd());
      context.put("has_prev", pagination.hasPrev());
      context.put("has_next", pagination.hasNext());

      // 过滤器回显值
      context.put("filter_agent", params.getOrDefault("agent", ""));
      context.put("filter_model", params.getOrDefault("model", ""));
      context.put("filter_project", params.getOrDefault("project", ""));
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("filter_status", params.getOrDefault("status", ""));
      context.put("sort_by", QueryParams.uiSortKey(params));
      context.put("sort_dir", params.getOrDefault("dir", "desc"));
      context.put("active_page", "sessions");

      String html = templates.render("sessions.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Sessions 页面查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(renderError(ctx, "查询会话列表失败"));
    }
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
