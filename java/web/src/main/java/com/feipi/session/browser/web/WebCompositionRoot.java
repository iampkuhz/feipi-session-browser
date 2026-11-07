package com.feipi.session.browser.web;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.index.api.IndexQueryException;
import com.feipi.session.browser.web.api.ApiResponses.ApiErrorResponse;
import com.feipi.session.browser.web.api.DashboardApiHandler;
import com.feipi.session.browser.web.api.ExportApiHandler;
import com.feipi.session.browser.web.api.GlossaryApiHandler;
import com.feipi.session.browser.web.api.ImportedSessionApiHandler;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateModel;
import com.feipi.session.browser.web.api.PageApiDtos.SafeErrorDetails;
import com.feipi.session.browser.web.api.ProjectDetailApiHandler;
import com.feipi.session.browser.web.api.ProjectsApiHandler;
import com.feipi.session.browser.web.api.SessionApiHandler;
import com.feipi.session.browser.web.api.SessionApiRouter;
import com.feipi.session.browser.web.api.SessionApiService;
import com.feipi.session.browser.web.api.SessionApiService.SessionDataException;
import com.feipi.session.browser.web.api.SessionDetailApiHandler;
import com.feipi.session.browser.web.api.SessionsApiHandler;
import com.feipi.session.browser.web.export.ExportHandler;
import com.feipi.session.browser.web.page.DashboardPage;
import com.feipi.session.browser.web.page.GlossaryPage;
import com.feipi.session.browser.web.page.ImportedSessionPage;
import com.feipi.session.browser.web.page.ProjectsPage;
import com.feipi.session.browser.web.page.SessionDetailPage;
import com.feipi.session.browser.web.page.SessionsPage;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.Javalin;
import io.javalin.config.SizeUnit;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import io.javalin.http.staticfiles.Location;
import java.io.IOException;
import java.time.Instant;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
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
  private final SessionApiService apiService;
  private final ImportedSessionUseCase imports;
  private final AtomicBoolean importsClosed = new AtomicBoolean();

  /**
   * 创建 Composition Root。
   *
   * <p>在构造期间创建 Javalin 实例、模板引擎并注册全部路由。
   *
   * @param queryRoot 查询 composition root，提供所有 use case
   * @param config Web 服务器配置
   */
  public WebCompositionRoot(QueryCompositionRoot queryRoot, WebConfig config) {
    this(queryRoot, config, null);
  }

  /**
   * 创建带独立文件分析的 Web 入口，个人查询入口保持原有职责。
   *
   * @param queryRoot 个人只读查询入口
   * @param config Web 配置
   * @param imports 独立导入用例；为 null 时不开放导入路由
   */
  public WebCompositionRoot(
      QueryCompositionRoot queryRoot, WebConfig config, ImportedSessionUseCase imports) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.config = Objects.requireNonNull(config, "config 不得为 null");
    this.imports = imports;
    this.templates = new PebbleEnvironment("templates", config.appVersion());
    this.apiService =
        new SessionApiService(
            queryRoot.sessionDetail()::getDetailContext, queryRoot::publishedGeneration);
    this.app =
        createAndConfigureJavalin(
            queryRoot, config, templates, apiService, imports, this::closeImportsSafely);
    LOG.debug("Web Composition Root 初始化完成");
  }

  /**
   * 创建并配置 Javalin 实例，注册全部路由和 handler。
   *
   * @param queryRoot 查询 composition root
   * @param config Web 服务器配置
   * @param templates Pebble 模板环境
   * @param apiService 个人详情 API 服务
   * @param imports 可选的独立文件分析用例
   * @param closeImports 生命周期终止时的资源清理
   * @return 配置完成的 Javalin 实例
   */
  private static Javalin createAndConfigureJavalin(
      QueryCompositionRoot queryRoot,
      WebConfig config,
      PebbleEnvironment templates,
      SessionApiService apiService,
      ImportedSessionUseCase imports,
      Runnable closeImports) {
    return Javalin.create(
        javalinConfig -> {
          configureHttp(javalinConfig);
          if (imports != null) {
            javalinConfig.events.serverStopped(closeImports::run);
            javalinConfig.events.serverStartFailed(closeImports::run);
            long maxFile = imports.limits().maxFileBytes();
            long maxRequest = Math.addExact(maxFile, 64L * 1024);
            javalinConfig.http.maxRequestSize = maxRequest;
            javalinConfig.jetty.multipartConfig.maxFileSize(maxFile, SizeUnit.BYTES);
            javalinConfig.jetty.multipartConfig.maxTotalRequestSize(maxRequest, SizeUnit.BYTES);
          }
          configureStaticFiles(javalinConfig, config);
          registerRoutes(javalinConfig, queryRoot, templates, apiService, imports);
          registerExceptionHandlers(javalinConfig, templates);
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
            staticConfig.directory = config.staticPath();
            if ("/static".equals(config.staticPath())) {
              staticConfig.hostedPath = "/static";
              staticConfig.location = Location.CLASSPATH;
            } else {
              staticConfig.hostedPath = "/";
            }
          });
    }
  }

  /** 注册全部路由。 */
  private static void registerRoutes(
      io.javalin.config.JavalinConfig javalinConfig,
      QueryCompositionRoot queryRoot,
      PebbleEnvironment templates,
      SessionApiService apiService,
      ImportedSessionUseCase imports) {

    // 访问日志：记录开始时间
    javalinConfig.routes.before(RuntimeAccessLog::before);

    // 全局安全头（CSP、X-Frame-Options 等），在所有路由前注入
    javalinConfig.routes.before(SecurityHeaders::apply);

    // 健康检查
    javalinConfig.routes.get("/healthz", WebServer::healthHandler);

    // 页面路由
    DashboardPage dashboardPage = new DashboardPage(queryRoot, templates);
    ProjectsPage projectsPage = new ProjectsPage(queryRoot, templates);
    SessionsPage sessionsPage = new SessionsPage(queryRoot, templates);
    SessionDetailPage sessionDetailPage = new SessionDetailPage(queryRoot, templates);
    GlossaryPage glossaryPage = new GlossaryPage(templates);

    IndexSnapshotGuard pageSnapshot = new IndexSnapshotGuard(queryRoot::publishedGeneration);
    javalinConfig.routes.get("/", pageSnapshot.wrapPage(dashboardPage::handle));
    javalinConfig.routes.get("/dashboard", pageSnapshot.wrapPage(dashboardPage::handle));
    javalinConfig.routes.get("/projects", pageSnapshot.wrapPage(projectsPage::handleList));
    javalinConfig.routes.get(
        "/projects/<key>",
        pageSnapshot.wrapPage(
            ctx -> {
              String key = ctx.pathParam("key");
              projectsPage.handleDetail(ctx, key);
            }));
    javalinConfig.routes.get("/sessions", pageSnapshot.wrapPage(sessionsPage::handle));
    javalinConfig.routes.get(
        "/sessions/{agent}/{sessionId}",
        pageSnapshot.wrapPage(
            ctx -> {
              String agentParam = ctx.pathParam("agent");
              String sessionIdParam = ctx.pathParam("sessionId");
              sessionDetailPage.handle(ctx, agentParam, sessionIdParam);
            }));
    javalinConfig.routes.get("/glossary", glossaryPage::handle);

    if (imports != null) {
      ImportedSessionPage importPage =
          new ImportedSessionPage(imports, templates, sessionDetailPage);
      ImportedSessionApiHandler importApi = new ImportedSessionApiHandler(imports);
      javalinConfig.routes.get("/imports", importPage::handleIndex);
      javalinConfig.routes.get("/imports/{importId}", importPage::handleDetail);
      javalinConfig.routes.post("/api/imports", importApi::handleCreate);
      javalinConfig.routes.delete("/api/imports/{importId}", importApi::handleDelete);
      javalinConfig.routes.get("/api/imports/{importId}/*", importApi::handleResource);
    }

    // JSON API 路由
    registerApiRoutes(javalinConfig, queryRoot, apiService);

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

    // 页面 handler 的 ctx.html() 会覆盖 defaultContentType；在响应提交前补齐 HTML charset。
    javalinConfig.routes.after(WebCompositionRoot::ensureHtmlCharset);

    // 访问日志：记录请求摘要
    javalinConfig.routes.after(RuntimeAccessLog::after);
  }

  /** 确保 HTML 响应显式声明 UTF-8，避免浏览器依赖内容嗅探。 */
  private static void ensureHtmlCharset(Context ctx) {
    String contentType = ctx.contentType();
    if (contentType == null) {
      return;
    }
    String normalized = contentType.toLowerCase(Locale.ROOT);
    if (normalized.startsWith("text/html") && !normalized.contains("charset=")) {
      ctx.contentType("text/html; charset=utf-8");
    }
  }

  /** 注册 JSON API 路由。 */
  private static void registerApiRoutes(
      io.javalin.config.JavalinConfig javalinConfig,
      QueryCompositionRoot queryRoot,
      SessionApiService apiService) {
    javalinConfig.routes.get(
        "/api/scan-status",
        new com.feipi.session.browser.web.api.ScanStatusApiHandler(queryRoot)::handle);
    IndexSnapshotGuard snapshot = new IndexSnapshotGuard(queryRoot::publishedGeneration);
    DashboardApiHandler dashboardApiHandler = new DashboardApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/dashboard/event-activity", snapshot.wrap(dashboardApiHandler::handleEventActivity));
    javalinConfig.routes.get(
        "/api/dashboard/summary", snapshot.wrap(dashboardApiHandler::handleSummary));
    javalinConfig.routes.get(
        "/api/dashboard/trends/sessions", snapshot.wrap(dashboardApiHandler::handleSessionsTrend));
    javalinConfig.routes.get(
        "/api/dashboard/trends/tokens", snapshot.wrap(dashboardApiHandler::handleTokenTrend));
    javalinConfig.routes.get(
        "/api/dashboard/trends/prompts", snapshot.wrap(dashboardApiHandler::handlePromptTrend));
    javalinConfig.routes.get(
        "/api/dashboard/trends/cache-health",
        snapshot.wrap(dashboardApiHandler::handleCacheHealth));
    javalinConfig.routes.get(
        "/api/dashboard/agents/contribution",
        snapshot.wrap(dashboardApiHandler::handleAgentContribution));
    javalinConfig.routes.get(
        "/api/dashboard/agents/efficiency",
        snapshot.wrap(dashboardApiHandler::handleAgentEfficiency));
    javalinConfig.routes.get(
        "/api/dashboard/agents/{agent}/deep-dive",
        snapshot.wrap(dashboardApiHandler::handleAgentDeepDive));

    ExportApiHandler exportApiHandler = new ExportApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/export/session/{agent}/{sessionId}/manifest", exportApiHandler::handleManifest);
    javalinConfig.routes.get(
        "/api/export/session/{agent}/{sessionId}/data-bundle", exportApiHandler::handleDataBundle);

    GlossaryApiHandler glossaryApiHandler = new GlossaryApiHandler();
    javalinConfig.routes.get("/api/glossary/summary", glossaryApiHandler::handleSummary);
    javalinConfig.routes.get("/api/glossary/token-types", glossaryApiHandler::handleTokenTypes);
    javalinConfig.routes.get(
        "/api/glossary/derived-metrics", glossaryApiHandler::handleDerivedMetrics);
    javalinConfig.routes.get(
        "/api/glossary/provider-mapping", glossaryApiHandler::handleProviderMapping);
    javalinConfig.routes.get(
        "/api/glossary/provider-mappings", glossaryApiHandler::handleProviderMapping);
    javalinConfig.routes.get("/api/glossary/round-signals", glossaryApiHandler::handleRoundSignals);

    ProjectsApiHandler projectsApiHandler = new ProjectsApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/projects/summary", snapshot.wrap(projectsApiHandler::handleSummary));
    javalinConfig.routes.get("/api/projects/rows", snapshot.wrap(projectsApiHandler::handleRows));
    javalinConfig.routes.get(
        "/api/projects/active-filters", snapshot.wrap(projectsApiHandler::handleActiveFilters));
    ProjectDetailApiHandler projectDetailApiHandler = new ProjectDetailApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/summary",
        snapshot.wrap(projectDetailApiHandler::handleSummary));
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/token-trend",
        snapshot.wrap(projectDetailApiHandler::handleTokenTrend));
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/agent-mix",
        snapshot.wrap(projectDetailApiHandler::handleAgentMix));
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/tool-hotspots",
        snapshot.wrap(projectDetailApiHandler::handleToolHotspots));
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/sessions/summary",
        snapshot.wrap(projectDetailApiHandler::handleSessionsSummary));
    javalinConfig.routes.get(
        "/api/projects/{projectKey}/sessions/rows",
        snapshot.wrap(projectDetailApiHandler::handleSessionsRows));

    SessionsApiHandler sessionsListApiHandler = new SessionsApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/sessions/summary", snapshot.wrap(sessionsListApiHandler::handleSummary));
    javalinConfig.routes.get(
        "/api/sessions/options", snapshot.wrap(sessionsListApiHandler::handleOptions));
    javalinConfig.routes.get(
        "/api/sessions/rows", snapshot.wrap(sessionsListApiHandler::handleRows));
    javalinConfig.routes.get(
        "/api/sessions/active-filters", snapshot.wrap(sessionsListApiHandler::handleActiveFilters));

    SessionDetailApiHandler sessionDetailApiHandler = new SessionDetailApiHandler(queryRoot);
    javalinConfig.routes.get(
        "/api/sessions/{agent}/{sessionId}/meta",
        snapshot.wrap(sessionDetailApiHandler::handleMeta));
    javalinConfig.routes.get(
        "/api/sessions/{agent}/{sessionId}/metrics",
        snapshot.wrap(sessionDetailApiHandler::handleMetrics));
    javalinConfig.routes.get(
        "/api/sessions/{agent}/{sessionId}/diagnostics",
        snapshot.wrap(sessionDetailApiHandler::handleDiagnostics));
    javalinConfig.routes.get(
        "/api/sessions/{agent}/{sessionId}/rounds",
        snapshot.wrap(sessionDetailApiHandler::handleRounds));
    javalinConfig.routes.get(
        "/api/sessions/{agent}/{sessionId}/payloads",
        snapshot.wrap(sessionDetailApiHandler::handlePayloads));

    SessionApiHandler apiHandler = new SessionApiHandler(apiService);
    SessionApiRouter apiRouter = new SessionApiRouter(apiHandler);

    javalinConfig.routes.get("/api/sessions/*", snapshot.wrap(apiRouter::route));
    javalinConfig.routes.get(
        "/api/*",
        ctx -> {
          ctx.status(HttpStatus.NOT_FOUND);
          ctx.json(new ApiErrorResponse("not_found", "资源不存在"));
        });
  }

  /** 注册异常和错误 handler。 */
  private static void registerExceptionHandlers(
      io.javalin.config.JavalinConfig javalinConfig, PebbleEnvironment templates) {
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
          if (isApiPath(ctx)) {
            ctx.json(new ApiErrorResponse("artifact_error", "归一化制品加载失败"));
          } else {
            ctx.html(renderErrorPage(templates, "归一化制品加载失败", "请稍后重试或检查制品数据。", ctx, e));
          }
        });

    javalinConfig.routes.exception(
        IndexQueryException.class,
        (e, ctx) -> {
          LOG.error("数据库查询失败", e);
          ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
          if (isApiPath(ctx)) {
            ctx.json(new ApiErrorResponse("internal_error", "查询失败"));
          } else {
            ctx.html(renderErrorPage(templates, "查询失败", "请稍后重试或检查索引数据库。", ctx, e));
          }
        });

    javalinConfig.routes.exception(
        Exception.class,
        (e, ctx) -> {
          LOG.error("未处理异常", e);
          ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
          if (isApiPath(ctx)) {
            ctx.json(new ApiErrorResponse("internal_error", "服务器内部错误"));
          } else {
            ctx.html(renderErrorPage(templates, "服务器内部错误", "请稍后重试。", ctx, e));
          }
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
            ctx.html(renderNotFoundPage(templates));
          }
        });
  }

  private static boolean isApiPath(Context ctx) {
    return ctx.path().startsWith("/api/");
  }

  private static String renderNotFoundPage(PebbleEnvironment templates) {
    PageStateModel state =
        PageStateModel.notFound("The page you're looking for doesn't exist or has been removed.");
    Map<String, Object> context = new HashMap<>();
    context.put("state", state);
    context.put("error", state.message());
    return templates.render("404.html", context);
  }

  private static String renderErrorPage(
      PebbleEnvironment templates, String error, String detail, Context ctx, Exception exception) {
    SafeErrorDetails safeDetails =
        new SafeErrorDetails(
            exception == null ? "" : exception.getClass().getSimpleName(),
            ctx == null ? "" : ctx.path(),
            UUID.randomUUID().toString(),
            Instant.now().toString(),
            exception == null ? error : error + ": " + exception.getMessage());
    PageStateModel state = PageStateModel.error(error, safeDetails);
    Map<String, Object> context = new HashMap<>();
    context.put("state", state);
    context.put("error", error);
    context.put("detail", detail);
    context.put("request_path", ctx == null ? "#" : ctx.path());
    context.put("error_details", safeDetails);
    return templates.render("error.html", context);
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
   * 失效全部缓存：查询缓存和详情 API 缓存。
   *
   * <p>扫描或数据变更后调用，确保后续请求读取新数据。
   */
  public void invalidateCache() {
    queryRoot.invalidateCache();
    apiService.invalidateCache();
  }

  /**
   * 释放独立分析资源，可在启动失败或退出清理时重复调用，不关闭个人索引。
   *
   * @throws IOException 导入资源清理失败
   */
  public void closeImports() throws IOException {
    if (imports != null && importsClosed.compareAndSet(false, true)) {
      imports.close();
    }
  }

  private void closeImportsSafely() {
    try {
      closeImports();
    } catch (IOException e) {
      LOG.warn("独立导入资源清理失败: {}", e.getClass().getSimpleName());
    }
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
