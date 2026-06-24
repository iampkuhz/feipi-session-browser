package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.DashboardRow;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Dashboard 页面路由处理器。
 *
 * <p>处理 {@code GET /} 和 {@code GET /dashboard} 请求：解析 agent scope 和 grain 参数， 调用 Dashboard use
 * case，组装模板上下文，渲染 HTML 响应。
 *
 * <p>Dashboard 页面的完整 KPI 计算和趋势图数据组装在后续 task 中增量迁移， 当前版本提供基础骨架：status code、content type、关键 DOM 和导航。
 */
public final class DashboardPage {

  private static final Logger LOG = LoggerFactory.getLogger(DashboardPage.class);
  private static final Set<String> VALID_AGENT_SCOPES =
      Set.of("all", "claude-code", "qoder", "codex");
  private static final Set<String> VALID_GRAINS = Set.of("day", "week", "month");

  /** scope URL 参数到 DB agent 值的映射。 */
  private static final Map<String, String> SCOPE_TO_DB =
      Map.of("claude-code", "claude_code", "qoder", "qoder", "codex", "codex");

  /** grain 到趋势窗口天数的映射。 */
  private static final Map<String, Integer> GRAIN_DAYS =
      Map.of("day", 30, "week", 140, "month", 360);

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Dashboard 页面处理器。
   *
   * @param queryRoot 查询 composition root
   * @param templates Pebble 模板环境
   */
  public DashboardPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET / 或 GET /dashboard 请求。
   *
   * @param ctx Javalin 请求上下文
   */
  public void handle(Context ctx) {
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);

    String agentScope = normalizeAgentScope(params.getOrDefault("agent", "all"));
    String grain = normalizeGrain(params.getOrDefault("grain", "day"));

    try {
      DashboardUseCase useCase = queryRoot.dashboard();

      // 全局统计
      AgentFilter agentFilter = buildAgentFilter(agentScope);
      DashboardRow stats = useCase.stats(agentFilter);

      // 趋势数据
      int days = GRAIN_DAYS.getOrDefault(grain, 30);
      TrendFilter trendFilter = TrendFilter.ofDays(days);
      if (!agentFilter.isUnfiltered()) {
        trendFilter = trendFilter.withAgent(agentFilter);
      }

      // 组装模板上下文
      Map<String, Object> context = new HashMap<>();
      context.put("stats", stats);
      context.put("agent_scope", agentScope);
      context.put("grain", grain);
      context.put("is_single_agent", !"all".equals(agentScope));
      context.put("active_page", "dashboard");

      String html = templates.render("dashboard.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Dashboard 查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render(
              "error.html", Map.of("error", "查询 Dashboard 数据失败", "active_page", "dashboard")));
    }
  }

  private static String normalizeAgentScope(String value) {
    if (value == null || !VALID_AGENT_SCOPES.contains(value)) {
      return "all";
    }
    return value;
  }

  private static String normalizeGrain(String value) {
    if (value == null || !VALID_GRAINS.contains(value)) {
      return "day";
    }
    return value;
  }

  private static AgentFilter buildAgentFilter(String agentScope) {
    if ("all".equals(agentScope)) {
      return AgentFilter.NONE;
    }
    String dbAgent = SCOPE_TO_DB.getOrDefault(agentScope, "");
    if (dbAgent.isEmpty()) {
      return AgentFilter.NONE;
    }
    return AgentFilter.of(dbAgent);
  }
}
