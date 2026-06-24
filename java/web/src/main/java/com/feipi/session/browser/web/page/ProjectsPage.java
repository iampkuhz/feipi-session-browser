package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.ProjectListUseCase;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.index.sqlite.SessionListAggregate;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.TitleFilter;
import com.feipi.session.browser.web.model.PaginationModel;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Projects 页面路由处理器。
 *
 * <p>处理两个路由：
 *
 * <ul>
 *   <li>{@code GET /projects} — 项目列表页
 *   <li>{@code GET /projects/{key}} — 项目详情页（包含该项目的会话列表）
 * </ul>
 *
 * <p>路由只负责 HTTP input 解析和 output 渲染，数据查询委托给 use case。
 */
public final class ProjectsPage {

  private static final Logger LOG = LoggerFactory.getLogger(ProjectsPage.class);

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Projects 页面处理器。
   *
   * @param queryRoot 查询 composition root
   * @param templates Pebble 模板环境
   */
  public ProjectsPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET /projects 列表请求。
   *
   * @param ctx Javalin 请求上下文
   */
  public void handleList(Context ctx) {
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);
    ProjectListFilter filter = QueryParams.parseProjectListFilter(params);

    try {
      ProjectListUseCase useCase = queryRoot.projectList();
      long totalCount = useCase.count(filter);
      var pageResult = useCase.list(filter);

      int currentPage = QueryParams.parsePage(params);
      int pageSize = QueryParams.parsePageSize(params);
      PaginationModel pagination = PaginationModel.of(currentPage, pageSize, (int) totalCount);

      Map<String, Object> context = new HashMap<>();
      context.put("projects", pageResult.items());
      context.put("total_count", totalCount);
      context.putAll(pagination.toTemplateContext());
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("sort_by", params.getOrDefault("sort", "last_active"));
      context.put("sort_dir", params.getOrDefault("dir", "desc"));
      context.put("active_page", "projects");

      String html = templates.render("projects.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Projects 列表查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render("error.html", Map.of("error", "查询项目列表失败", "active_page", "projects")));
    }
  }

  /**
   * 处理 GET /projects/{key} 详情请求。
   *
   * @param ctx Javalin 请求上下文
   * @param projectKey URL 中的项目键
   */
  public void handleDetail(Context ctx, String projectKey) {
    String decodedKey = URLDecoder.decode(projectKey, StandardCharsets.UTF_8);
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);

    try {
      ProjectListUseCase projectUseCase = queryRoot.projectList();
      ProjectStatsRow project = projectUseCase.stats(decodedKey);

      // 项目不存在时返回 404
      if (project.totalSessions() == 0
          && (project.projectName() == null || project.projectName().isEmpty())) {
        ctx.status(HttpStatus.NOT_FOUND);
        ctx.html(
            templates.render("error.html", Map.of("error", "项目不存在", "active_page", "projects")));
        return;
      }

      // 查询该项目下的会话列表
      SessionListFilter sessionFilter = buildProjectSessionFilter(decodedKey, params);
      SessionListUseCase sessionUseCase = queryRoot.sessionList();
      long totalCount = sessionUseCase.count(sessionFilter);
      SessionListUseCase.AnnotatedPageResult result =
          sessionUseCase.listWithAnomalies(sessionFilter);
      SessionListAggregate aggregate = sessionUseCase.aggregate(sessionFilter);

      int currentPage = QueryParams.parsePage(params);
      int pageSize = QueryParams.parsePageSize(params);
      PaginationModel pagination = PaginationModel.of(currentPage, pageSize, (int) totalCount);

      Map<String, Object> context = new HashMap<>();
      context.put("project", project);
      context.put("sessions", result.page().items());
      context.put("anomalies", result.anomalies());
      context.put("sessions_aggregate", aggregate);
      context.put("project_key", decodedKey);
      context.put("total_count", totalCount);
      context.putAll(pagination.toTemplateContext());
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("sort_by", QueryParams.uiSortKey(params));
      context.put("sort_dir", params.getOrDefault("dir", "desc"));
      context.put("active_page", "projects");

      String html = templates.render("project.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Project 详情查询失败: {}", decodedKey, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render("error.html", Map.of("error", "查询项目详情失败", "active_page", "projects")));
    }
  }

  /**
   * 构建项目详情页的会话列表过滤器。
   *
   * @param projectKey 项目键
   * @param params 查询参数
   * @return 限定到指定项目的会话列表过滤器
   */
  private static SessionListFilter buildProjectSessionFilter(
      String projectKey, Map<String, String> params) {
    SessionListFilter filter = SessionListFilter.defaults();
    filter = filter.withProject(ProjectFilter.of(projectKey));

    String q = params.getOrDefault("q", "").trim();
    if (!q.isEmpty()) {
      filter = filter.withTitle(TitleFilter.of(q));
    }

    // 项目详情页的排序默认按 ended_at DESC
    String rawSort = params.getOrDefault("sort", "").trim().toLowerCase();
    String rawDir = params.getOrDefault("dir", "desc").trim().toLowerCase();
    String dir = ("asc".equals(rawDir)) ? "asc" : "desc";
    if (!rawSort.isEmpty()) {
      String dbField = QueryParams.resolveSessionSortField(rawSort, "ended_at");
      filter = filter.withSort(Sort.ofSession(dbField, dir));
    }

    int page = QueryParams.parsePage(params);
    int pageSize = QueryParams.parsePageSize(params);
    int offset = (page - 1) * pageSize;
    filter = filter.withPage(PageRequest.ofOffset(offset, pageSize));

    return filter;
  }
}
