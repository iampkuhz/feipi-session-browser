package com.feipi.session.browser.web;

import io.javalin.http.Context;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * HTTP 请求访问日志。
 *
 * <p>记录业务页面和 API 请求的 method、安全路由分类、status 和耗时。 过滤静态资源和健康检查，避免刷屏。 不记录原始
 * URL、query、header、body、token、session id 或个人路径。
 */
final class RuntimeAccessLog {

  private static final Logger LOG = LoggerFactory.getLogger(RuntimeAccessLog.class);

  private static final String START_TIME_ATTR = "runtime.access.startTime";
  private static final String ROUTE_CATEGORY_ATTR = "runtime.access.routeCategory";

  private RuntimeAccessLog() {}

  /** Javalin before handler：记录开始时间和路由分类。 */
  static void before(Context ctx) {
    ctx.attribute(START_TIME_ATTR, System.nanoTime());
    ctx.attribute(ROUTE_CATEGORY_ATTR, classifyRoute(ctx.path()));
  }

  /** Javalin after handler：记录访问日志。 */
  static void after(Context ctx) {
    String routeCategory = ctx.attribute(ROUTE_CATEGORY_ATTR);
    if (routeCategory == null || "skip".equals(routeCategory)) {
      return;
    }

    Long startNanos = ctx.attribute(START_TIME_ATTR);
    long elapsedMs = startNanos != null ? (System.nanoTime() - startNanos) / 1_000_000 : -1;

    String method = ctx.method().name();
    int status = ctx.status().getCode();

    LOG.info("{} {} {} {}ms", method, routeCategory, status, elapsedMs);
  }

  /**
   * 将请求路径分类为安全的路由类别。
   *
   * <p>使用路径段数量和位置进行分类，避免用户可控的 agent/sessionId/project key 影响端点类型判断。 不暴露 session id、project key
   * 或其他参数。未匹配的路径返回 "unknown"。 需要跳过的路径（healthz、static）返回 "skip"。
   */
  static String classifyRoute(String path) {
    if ("/healthz".equals(path) || path.startsWith("/static/")) {
      return "skip";
    }

    if ("/".equals(path)) return "page:/";
    if ("/dashboard".equals(path)) return "page:/dashboard";
    if ("/projects".equals(path)) return "page:/projects";
    if (path.startsWith("/projects/")) return "page:/projects/{key}";
    if ("/sessions".equals(path)) return "page:/sessions";
    if (path.startsWith("/sessions/") && path.endsWith("/export.html")) {
      return "page:/sessions/{agent}/{sessionId}/export.html";
    }
    if (path.startsWith("/sessions/")) return "page:/sessions/{agent}/{sessionId}";
    if ("/glossary".equals(path)) return "page:/glossary";
    if (path.startsWith("/export/")) return "page:/export/{format}";

    if (path.startsWith("/api/")) {
      return classifyApi(path);
    }

    return "unknown";
  }

  private static String classifyApi(String path) {
    String[] segments = path.split("/");
    // 段数组结构：segments[0] 为首斜杠前的空串，segments[1] = "api"，segments[2] = 资源类型

    if (path.startsWith("/api/dashboard/")) {
      return classifyDashboardApi(path);
    }

    if (path.startsWith("/api/glossary/")) {
      return classifyGlossaryApi(path);
    }

    if (path.startsWith("/api/export/session/")) {
      // 导出接口路径结构：7 段，依次为 agent、sessionId、action
      if (segments.length == 7) {
        String action = segments[6];
        if ("manifest".equals(action))
          return "api:/api/export/session/{agent}/{sessionId}/manifest";
        if ("data-bundle".equals(action))
          return "api:/api/export/session/{agent}/{sessionId}/data-bundle";
      }
      return "api:/api/export/session/{agent}/{sessionId}/*";
    }

    if (path.startsWith("/api/projects/")) {
      return classifyProjectApi(path);
    }

    if (path.startsWith("/api/sessions/")) {
      return classifySessionsApi(path, segments);
    }

    return "unknown";
  }

  private static String classifyDashboardApi(String path) {
    if (path.startsWith("/api/dashboard/trends/")) return "api:/api/dashboard/trends/{metric}";
    if (path.startsWith("/api/dashboard/agents/")) return "api:/api/dashboard/agents/{type}";
    if ("/api/dashboard/summary".equals(path)) return "api:/api/dashboard/summary";
    return "api:/api/dashboard/*";
  }

  private static String classifyGlossaryApi(String path) {
    if ("/api/glossary/summary".equals(path)) return "api:/api/glossary/summary";
    if ("/api/glossary/token-types".equals(path)) return "api:/api/glossary/token-types";
    if ("/api/glossary/derived-metrics".equals(path)) return "api:/api/glossary/derived-metrics";
    if ("/api/glossary/provider-mapping".equals(path)) return "api:/api/glossary/provider-mapping";
    if ("/api/glossary/provider-mappings".equals(path))
      return "api:/api/glossary/provider-mappings";
    if ("/api/glossary/round-signals".equals(path)) return "api:/api/glossary/round-signals";
    return "api:/api/glossary/*";
  }

  private static String classifyProjectApi(String path) {
    if ("/api/projects/summary".equals(path)) return "api:/api/projects/summary";
    if ("/api/projects/rows".equals(path)) return "api:/api/projects/rows";
    if ("/api/projects/active-filters".equals(path)) return "api:/api/projects/active-filters";
    // project key 可能包含斜杠，通过后缀匹配识别已知端点
    if (path.endsWith("/sessions/summary")) return "api:/api/projects/{key}/sessions/summary";
    if (path.endsWith("/sessions/rows")) return "api:/api/projects/{key}/sessions/rows";
    if (path.endsWith("/token-trend")) return "api:/api/projects/{key}/token-trend";
    if (path.endsWith("/agent-mix")) return "api:/api/projects/{key}/agent-mix";
    if (path.endsWith("/tool-hotspots")) return "api:/api/projects/{key}/tool-hotspots";
    if (path.endsWith("/summary")) return "api:/api/projects/{key}/summary";
    if (path.endsWith("/rows")) return "api:/api/projects/{key}/rows";
    if (path.endsWith("/active-filters")) return "api:/api/projects/{key}/active-filters";
    return "api:/api/projects/{key}/*";
  }

  private static String classifySessionsApi(String path, String[] segments) {
    // 列表接口 4 段：["", "api", "sessions", "{action}"]
    // 详情接口 6 段：["", "api", "sessions", "{agent}", "{sessionId}", "{action}"]
    // 5 段为兜底分类

    if (segments.length == 4) {
      // 列表接口：/api/sessions/{action}
      String action = segments[3];
      if ("summary".equals(action)) return "api:/api/sessions/summary";
      if ("options".equals(action)) return "api:/api/sessions/options";
      if ("rows".equals(action)) return "api:/api/sessions/rows";
      if ("active-filters".equals(action)) return "api:/api/sessions/active-filters";
      return "api:/api/sessions/*";
    }

    if (segments.length == 6) {
      // 详情接口：/api/sessions/{agent}/{sessionId}/{action}
      String action = segments[5];
      if ("meta".equals(action)) return "api:/api/sessions/{agent}/{sessionId}/meta";
      if ("metrics".equals(action)) return "api:/api/sessions/{agent}/{sessionId}/metrics";
      if ("diagnostics".equals(action)) return "api:/api/sessions/{agent}/{sessionId}/diagnostics";
      if ("rounds".equals(action)) return "api:/api/sessions/{agent}/{sessionId}/rounds";
      if ("payloads".equals(action)) return "api:/api/sessions/{agent}/{sessionId}/payloads";
      return "api:/api/sessions/{agent}/{sessionId}/*";
    }

    // 兜底分类
    return "api:/api/sessions/*";
  }
}
