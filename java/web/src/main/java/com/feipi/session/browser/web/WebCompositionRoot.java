package com.feipi.session.browser.web;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.web.api.ApiResponses.ApiErrorResponse;
import com.feipi.session.browser.web.api.SessionApiHandler;
import com.feipi.session.browser.web.api.SessionApiRouter;
import com.feipi.session.browser.web.api.SessionApiService;
import com.feipi.session.browser.web.api.SessionApiService.SessionDataException;
import com.feipi.session.browser.web.export.ExportHandler;
import com.feipi.session.browser.web.page.DashboardPage;
import com.feipi.session.browser.web.page.ProjectsPage;
import com.feipi.session.browser.web.page.SessionDetailPage;
import com.feipi.session.browser.web.page.SessionsPage;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.Javalin;
import io.javalin.http.HttpStatus;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Web 层 Composition Root。
 *
 * <p>集中装配 Web 服务器所需的全部依赖：Javalin 实例、application use case、模板引擎、异常处理。 不使用 Spring/DI
 * framework，所有依赖通过构造器显式注入。
 *
 * <p>Javalin 7 的路由注册必须在 {@code Javalin.create(config -> ...)} lambda 内完成， 本类通过 {@code
 * config.routes} 注册全部路由、异常 handler 和错误 handler。
 *
 * <p>职责：
 *
 * <ul>
 *   <li>创建和配置 Javalin 实例（内容类型、静态资源、异常处理）
 *   <li>创建 Pebble 模板引擎
 *   <li>注册健康检查、Dashboard、Projects、Sessions、Session Detail 路由
 *   <li>注册 JSON API 路由（payload、round、attribution、bucket-detail）
 *   <li>将 {@link QueryCompositionRoot} 的 use case 绑定到路由
 * </ul>
 */
public final class WebCompositionRoot {

  private static final Logger LOG = LoggerFactory.getLogger(WebCompositionRoot.class);

  private final Javalin app;
  private final QueryCompositionRoot queryRoot;
  private final WebConfig config;
  private final PebbleEnvironment templates;

  /**
   * 创建 Composition Root。
   *
   * <p>在构造期间创建 Javalin 实例、模板引擎并注册全部路由。
   *
   * @param queryRoot 查询 composition root，提供所有 use case
   * @param config Web 服务器配置
   */
  public WebCompositionRoot(QueryCompositionRoot queryRoot, WebConfig config) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.config = Objects.requireNonNull(config, "config 不得为 null");
    this.templates = new PebbleEnvironment();
    this.app = createAndConfigureJavalin(queryRoot, config, templates);
    LOG.debug("Web Composition Root 初始化完成");
  }

  /**
   * 创建并配置 Javalin 实例，注册全部路由和 handler。
   *
   * @param queryRoot 查询 composition root
   * @param config Web 服务器配置
   * @param templates Pebble 模板环境
   * @return 配置完成的 Javalin 实例
   */
  private static Javalin createAndConfigureJavalin(
      QueryCompositionRoot queryRoot, WebConfig config, PebbleEnvironment templates) {
    return Javalin.create(
        javalinConfig -> {
          configureHttp(javalinConfig);
          configureStaticFiles(javalinConfig, config);
          registerRoutes(javalinConfig, queryRoot, templates);
          registerExceptionHandlers(javalinConfig);
        });
  }

  /** 配置 HTTP 基础参数。 */
  private static void configureHttp(io.javalin.config.JavalinConfig javalinConfig) {
    javalinConfig.http.defaultContentType = "text/html; charset=utf-8";
  }

  /** 配置静态资源路径。 */
  private static void configureStaticFiles(
      io.javalin.config.JavalinConfig javalinConfig, WebConfig config) {
    if (config.staticPath() != null) {
      javalinConfig.staticFiles.add(
          staticConfig -> {
            staticConfig.hostedPath = "/";
            staticConfig.directory = config.staticPath();
          });
    }
  }

  /** 注册全部路由。 */
  private static void registerRoutes(
      io.javalin.config.JavalinConfig javalinConfig,
      QueryCompositionRoot queryRoot,
      PebbleEnvironment templates) {

    // 全局安全头（CSP、X-Frame-Options 等），在所有路由前注入
    javalinConfig.routes.before(SecurityHeaders::apply);

    // 健康检查
    javalinConfig.routes.get("/healthz", WebServer::healthHandler);

    // 页面路由
    DashboardPage dashboardPage = new DashboardPage(queryRoot, templates);
    ProjectsPage projectsPage = new ProjectsPage(queryRoot, templates);
    SessionsPage sessionsPage = new SessionsPage(queryRoot, templates);
    SessionDetailPage sessionDetailPage = new SessionDetailPage(queryRoot, templates);

    javalinConfig.routes.get("/", dashboardPage::handle);
    javalinConfig.routes.get("/dashboard", dashboardPage::handle);
    javalinConfig.routes.get("/projects", projectsPage::handleList);
    javalinConfig.routes.get(
        "/projects/{key}",
        ctx -> {
          String key = ctx.pathParam("key");
          projectsPage.handleDetail(ctx, key);
        });
    javalinConfig.routes.get("/sessions", sessionsPage::handle);
    javalinConfig.routes.get(
        "/sessions/{agent}/{sessionId}",
        ctx -> {
          String agentParam = ctx.pathParam("agent");
          String sessionIdParam = ctx.pathParam("sessionId");
          sessionDetailPage.handle(ctx, agentParam, sessionIdParam);
        });

    // JSON API 路由
    registerApiRoutes(javalinConfig, queryRoot);

    // 导出路由
    ExportHandler exportHandler = new ExportHandler(templates, queryRoot);
    javalinConfig.routes.get("/export/{format}", exportHandler::handleExport);
    javalinConfig.routes.get(
        "/sessions/{agent}/{sessionId}/export.html",
        ctx -> {
          String agentParam = ctx.pathParam("agent");
          String sessionIdParam = ctx.pathParam("sessionId");
          exportHandler.exportSessionHtml(ctx, agentParam, sessionIdParam);
        });
  }

  /** 注册 JSON API 路由。 */
  private static void registerApiRoutes(
      io.javalin.config.JavalinConfig javalinConfig, QueryCompositionRoot queryRoot) {
    com.feipi.session.browser.index.sqlite.SessionQueryRepository sessionQueryRepo =
        new com.feipi.session.browser.index.sqlite.SessionQueryRepository(
            queryRoot.indexConnection());
    com.feipi.session.browser.index.sqlite.SessionDetailRepository detailRepo =
        new com.feipi.session.browser.index.sqlite.SessionDetailRepository(sessionQueryRepo);
    SessionApiService apiService = new SessionApiService(detailRepo);
    SessionApiHandler apiHandler = new SessionApiHandler(apiService);
    SessionApiRouter apiRouter = new SessionApiRouter(apiHandler);

    javalinConfig.routes.get("/api/sessions/*", apiRouter::route);
  }

  /** 注册异常和错误 handler。 */
  private static void registerExceptionHandlers(io.javalin.config.JavalinConfig javalinConfig) {
    javalinConfig.routes.exception(
        IllegalArgumentException.class,
        (e, ctx) -> {
          LOG.debug("请求参数错误: {}", e.getMessage());
          ctx.status(HttpStatus.BAD_REQUEST);
          ctx.json(new ApiErrorResponse("bad_request", e.getMessage()));
        });

    javalinConfig.routes.exception(
        SessionDataException.class,
        (e, ctx) -> {
          LOG.error("制品数据加载失败", e);
          ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
          ctx.json(new ApiErrorResponse("artifact_error", "归一化制品加载失败"));
        });

    javalinConfig.routes.exception(
        java.sql.SQLException.class,
        (e, ctx) -> {
          LOG.error("数据库查询失败", e);
          ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
          ctx.json(new ApiErrorResponse("internal_error", "查询失败"));
        });

    javalinConfig.routes.exception(
        Exception.class,
        (e, ctx) -> {
          LOG.error("未处理异常", e);
          ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
          ctx.json(new ApiErrorResponse("internal_error", "服务器内部错误"));
        });

    javalinConfig.routes.error(
        HttpStatus.NOT_FOUND,
        ctx -> {
          String customHtml = ctx.attribute("custom_error_html");
          if (customHtml != null) {
            ctx.html(customHtml);
          } else if (ctx.path().startsWith("/api/")) {
            // JSON API 路由的 404 已由 handler 写入，不覆盖
            if (ctx.resultInputStream() == null) {
              ctx.json(new ApiErrorResponse("not_found", "资源不存在"));
            }
          } else {
            ctx.json(new ApiErrorResponse("not_found", "资源不存在"));
          }
        });
  }

  /**
   * 创建 Web 服务器实例。
   *
   * @return 可启动的 Web 服务器
   */
  public WebServer createServer() {
    return new WebServer(app, config);
  }

  /**
   * 返回底层 Javalin 实例。
   *
   * <p>供测试或高级配置使用。
   *
   * @return Javalin 实例
   */
  public Javalin app() {
    return app;
  }

  /**
   * 返回查询 composition root。
   *
   * @return 查询 composition root
   */
  public QueryCompositionRoot queryRoot() {
    return queryRoot;
  }

  /**
   * 返回模板引擎。
   *
   * @return Pebble 模板环境
   */
  public PebbleEnvironment templates() {
    return templates;
  }
}
