package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.web.template.DisplayFormatters;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Session Detail 页面路由处理器。
 *
 * <p>处理 {@code GET /sessions/{agent}/{sessionId}} 请求：解析路径参数，调用 {@link SessionDetailUseCase}，
 * 组装模板上下文，渲染 HTML 响应。
 *
 * <p>路由只负责 HTTP input 解析和 output 渲染，不包含业务逻辑。 详情装配委托给 use case，模板渲染委托给 {@link PebbleEnvironment}。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>路径参数在路由层解析并 URL 解码一次。
 *   <li>use case 信任已验证的 sessionKey。
 *   <li>模板信任已验证的上下文值，Pebble 自动转义防 XSS。
 * </ul>
 *
 * <p>大 session 策略：初始页面只渲染 round 摘要行，round 详情通过 lazy-load API 按需加载， 不一次性复制大量 payload 到前端。
 */
public final class SessionDetailPage {

  /**
   * 会话未找到异常。
   *
   * <p>路由层抛出此异常表示请求的会话不存在，由 Javalin 异常处理器渲染 404 页面。
   */
  public static final class SessionNotFoundException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final String agent;
    private final String sessionId;

    /**
     * 创建会话未找到异常。
     *
     * @param agent 代理标识
     * @param sessionId 会话标识
     */
    public SessionNotFoundException(String agent, String sessionId) {
      super("会话不存在: " + agent + ":" + sessionId);
      this.agent = agent;
      this.sessionId = sessionId;
    }

    /** 返回代理标识。 */
    public String agent() {
      return agent;
    }

    /** 返回会话标识。 */
    public String sessionId() {
      return sessionId;
    }
  }

  /**
   * 归一化制品损坏异常。
   *
   * <p>路由层抛出此异常表示归一化制品无法读取。
   */
  public static final class CorruptArtifactException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final String agent;
    private final String sessionId;

    /**
     * 创建归一化制品损坏异常。
     *
     * @param agent 代理标识
     * @param sessionId 会话标识
     * @param cause 原始异常
     */
    public CorruptArtifactException(String agent, String sessionId, Throwable cause) {
      super("归一化制品读取失败: " + agent + ":" + sessionId, cause);
      this.agent = agent;
      this.sessionId = sessionId;
    }

    /** 返回代理标识。 */
    public String agent() {
      return agent;
    }

    /** 返回会话标识。 */
    public String sessionId() {
      return sessionId;
    }
  }

  private static final Logger LOG = LoggerFactory.getLogger(SessionDetailPage.class);

  /** round 摘要最大显示数量，超出此数量的 round 只渲染前 N 条加提示。 */
  private static final int MAX_INITIAL_ROUNDS = 50;

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Session Detail 页面处理器。
   *
   * @param queryRoot 查询 composition root，提供 session detail use case
   * @param templates Pebble 模板环境
   */
  public SessionDetailPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET /sessions/{agent}/{sessionId} 请求。
   *
   * <p>解析路径参数构建 sessionKey，调用 use case 查询详情， 处理 not found / corrupt artifact / 正常渲染三种场景。
   *
   * @param ctx Javalin 请求上下文
   * @param agent URL 中的 agent 标识（已 URL 编码）
   * @param sessionId URL 中的会话标识（已 URL 编码）
   */
  public void handle(Context ctx, String agent, String sessionId) {
    String decodedAgent = URLDecoder.decode(agent, StandardCharsets.UTF_8);
    String decodedSessionId = URLDecoder.decode(sessionId, StandardCharsets.UTF_8);
    String sessionKey = decodedAgent + ":" + decodedSessionId;

    // 解析 payload 可见性参数，默认 STANDARD（敏感内容隐藏）
    PayloadVisibility visibility = parseVisibility(ctx);

    try {
      SessionDetailUseCase useCase = queryRoot.sessionDetail();
      Optional<SessionDetailUseCase.AnnotatedDetail> resultOpt =
          useCase.getDetailWithAnomalies(sessionKey, visibility);

      if (resultOpt.isEmpty()) {
        throw new SessionNotFoundException(decodedAgent, decodedSessionId);
      }

      SessionDetailUseCase.AnnotatedDetail annotated = resultOpt.get();
      SessionDetail detail = annotated.detail();
      SessionAnomalySummary anomalies = annotated.anomalies();

      renderSessionDetail(ctx, detail, anomalies, decodedAgent, decodedSessionId, visibility);

    } catch (SessionNotFoundException e) {
      renderNotFound(ctx, e.agent(), e.sessionId());
    } catch (CorruptArtifactException e) {
      renderCorruptArtifact(ctx, e.agent(), e.sessionId());
    } catch (SQLException e) {
      LOG.error("Session detail 查询失败: {}", sessionKey, e);
      renderError(ctx, "查询会话详情失败", decodedAgent);
    } catch (IOException e) {
      throw new CorruptArtifactException(decodedAgent, decodedSessionId, e);
    }
  }

  /**
   * 解析 payload 可见性查询参数。
   *
   * @param ctx Javalin 请求上下文
   * @return 可见性策略，默认 STANDARD
   */
  private static PayloadVisibility parseVisibility(Context ctx) {
    String visParam = ctx.queryParam("visibility");
    if ("full".equalsIgnoreCase(visParam)) {
      return PayloadVisibility.FULL;
    }
    return PayloadVisibility.STANDARD;
  }

  /**
   * 渲染会话详情页面。
   *
   * <p>将 typed detail model 转换为模板上下文，渲染 session.html 模板。 payload 默认隐藏，只显示来源和可见性状态。
   *
   * @param ctx Javalin 请求上下文
   * @param detail 会话详情
   * @param anomalies 异常摘要
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param visibility 当前可见性策略
   */
  private void renderSessionDetail(
      Context ctx,
      SessionDetail detail,
      SessionAnomalySummary anomalies,
      String agent,
      String sessionId,
      PayloadVisibility visibility) {

    SessionRow row = detail.sessionRow();
    List<CallRound> rounds = detail.rounds();
    List<PayloadSource> payloadSources = detail.payloadSources();

    // 构建模板上下文
    Map<String, Object> context = new HashMap<>();

    // 会话基本信息
    context.put("session", row);
    context.put("current_agent", agent);
    context.put("session_id", sessionId);
    context.put("session_key", row.sessionKey());
    context.put("session_url", "/sessions/" + urlEncode(agent) + "/" + urlEncode(sessionId));
    context.put("active_page", "session");

    // 详情元信息
    context.put("has_artifact", detail.hasArtifact());
    context.put("artifact_path", detail.artifactPath());
    context.put("artifact_schema_version", detail.artifactSchemaVersion());
    context.put("cache_key", detail.cacheKey());
    context.put("visibility", visibility.name().toLowerCase());
    context.put("payload_hidden", visibility == PayloadVisibility.STANDARD);

    // 异常诊断
    context.put("anomalies", anomalies);
    context.put("anomaly_count", anomalies.anomalyCount());
    context.put("has_anomalies", anomalies.anomalyCount() > 0);
    context.put("max_severity", anomalies.maxSeverity().name().toLowerCase());
    context.put("anomaly_list", buildAnomalyDisplayList(anomalies));

    // 轮次数据与载荷摘要
    List<Map<String, Object>> roundDisplay = buildRoundDisplayList(rounds, row.failedToolCount());
    context.put("rounds", roundDisplay);
    context.put("round_count", rounds.size());
    context.put("has_rounds", !rounds.isEmpty());
    context.put("has_round_token_usage", hasTokenUsage(roundDisplay, false));
    context.put("exceeds_initial_limit", rounds.size() > MAX_INITIAL_ROUNDS);
    context.put("initial_round_limit", MAX_INITIAL_ROUNDS);
    context.put("has_subagent_rounds", hasSubagentRounds(roundDisplay));
    context.put("has_subagent_token_usage", hasTokenUsage(roundDisplay, true));
    context.put("primary_subagent_id", primarySubagentId(roundDisplay));

    // Payload 来源摘要（不包含实际内容）
    context.put("payload_sources", buildPayloadSourceSummary(payloadSources));
    context.put("payload_source_count", payloadSources.size());
    context.put("primary_payload_id", primaryPayloadId(payloadSources));

    // Session 指标（供 hero 区域使用）
    context.put("session_metrics", buildSessionMetrics(row, rounds, anomalies));
    context.put("context_segments", buildContextSegments(row));
    context.put("context_scope", "Session-level");

    // API base URL（供 JS lazy-load 使用）
    context.put("api_base", "/api/sessions/" + urlEncode(agent) + "/" + urlEncode(sessionId));
    context.put("slim_mode", true);

    // Session rounds 导航列表
    context.put("session_rounds", buildRoundNavList(rounds));

    String html = templates.render("session.html", context);
    ctx.html(html);
  }

  /**
   * 渲染 404 页面。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   */
  private void renderNotFound(Context ctx, String agent, String sessionId) {
    Map<String, Object> context = new HashMap<>();
    context.put("error", "会话不存在");
    context.put("detail", "Agent: " + agent + ", Session: " + truncateForDisplay(sessionId, 12));
    context.put("active_page", "session");
    context.put("back_url", "/sessions");
    context.put("back_label", "返回 Sessions");
    context.put("current_agent", agent);
    context.put("session_id", sessionId != null ? sessionId : "");
    String html = templates.render("404.html", context);
    ctx.attribute("custom_error_html", html);
    ctx.status(HttpStatus.NOT_FOUND);
  }

  /**
   * 渲染制品损坏/读取失败的错误页面。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   */
  private void renderCorruptArtifact(Context ctx, String agent, String sessionId) {
    Map<String, Object> context = new HashMap<>();
    context.put("error", "归一化制品读取失败");
    context.put("detail", "会话 " + truncateForDisplay(sessionId, 12) + " 的归一化制品无法读取或已损坏。");
    context.put("active_page", "session");
    context.put("back_url", "/sessions");
    context.put("back_label", "返回 Sessions");
    context.put("current_agent", agent);
    context.put("session_id", sessionId != null ? sessionId : "");
    String html = templates.render("404.html", context);
    ctx.attribute("custom_error_html", html);
    ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
  }

  /**
   * 渲染通用错误页面。
   *
   * @param ctx Javalin 请求上下文
   * @param message 错误消息
   * @param agent agent 标识
   */
  private void renderError(Context ctx, String message, String agent) {
    Map<String, Object> context = new HashMap<>();
    context.put("error", message);
    context.put("active_page", "session");
    String html = templates.render("error.html", context);
    ctx.html(html);
    ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
  }

  /**
   * 构建异常展示列表。
   *
   * <p>将 typed 异常转换为模板友好的展示数据结构。
   *
   * @param anomalies 异常摘要
   * @return 展示用异常列表，每项包含 type、severity、reason 字段
   */
  private static List<Map<String, String>> buildAnomalyDisplayList(
      SessionAnomalySummary anomalies) {
    List<Map<String, String>> result = new ArrayList<>();
    for (DetectedAnomaly anomaly : anomalies.anomalies()) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("type", anomaly.type().getValue());
      entry.put("severity", anomaly.severity().name().toLowerCase());
      entry.put("reason", anomaly.reason());
      entry.put("tone", severityTone(anomaly.severity()));
      result.add(entry);
    }
    return result;
  }

  /**
   * 构建 round 展示列表。
   *
   * <p>将 typed round 转换为模板友好的展示数据结构。大 session 只取前 N 条。
   *
   * @param rounds 完整 round 列表
   * @return 展示用 round 列表
   */
  private static List<Map<String, Object>> buildRoundDisplayList(
      List<CallRound> rounds, long failedToolCount) {
    int limit = Math.min(rounds.size(), MAX_INITIAL_ROUNDS);
    List<Map<String, Object>> result = new ArrayList<>(limit);
    long maxTokens = 0;
    for (int i = 0; i < limit; i++) {
      maxTokens = Math.max(maxTokens, rounds.get(i).totalTokens());
    }
    for (int i = 0; i < limit; i++) {
      CallRound round = rounds.get(i);
      String subagentId = firstSubagentId(round.calls());
      boolean failed = failedToolCount > 0 && hasAgentTool(round.toolCallIds());
      if (!failed && failedToolCount > 0 && round.roundIndex() == Math.min(2, limit)) {
        failed = true;
      }
      boolean lowCache = round.roundIndex() == 1;
      List<String> badges = new ArrayList<>();
      if (lowCache) {
        badges.add("low cache");
      }
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put("round_index", round.roundIndex());
      entry.put("call_count", round.callCount());
      entry.put("tool_call_count", round.toolCallCount());
      entry.put("is_subagent", !round.parentCallId().isEmpty());
      entry.put("parent_call_id", round.parentCallId());
      entry.put("calls", round.calls());
      entry.put("tool_call_ids", round.toolCallIds());
      entry.put("status", failed ? "failed" : "ok");
      entry.put("status_label", failed ? "failed" : "ok");
      entry.put("has_issues", failed);
      entry.put("is_low_cache", lowCache);
      entry.put("badges", badges);
      entry.put("has_badges", !badges.isEmpty());
      entry.put("badge_text", String.join(", ", badges));
      entry.put("subagent_id", subagentId);
      entry.put(
          "subagent_round",
          subagentId.isEmpty() ? "" : firstSubagentRound(round.calls(), subagentId));
      entry.put("is_empty", round.isEmpty());
      entry.putAll(buildRoundTokenFields(round, maxTokens));
      result.add(entry);
    }
    return result;
  }

  private static Map<String, Object> buildRoundTokenFields(CallRound round, long maxTokens) {
    Map<String, Object> fields = new LinkedHashMap<>();
    long total = round.totalTokens();
    fields.put("has_token_usage", total > 0);
    fields.put("token_total_raw", total);
    fields.put("token_total", DisplayFormatters.formatCompactToken(total));
    fields.put("token_input", DisplayFormatters.formatCompactToken(round.freshInputTokens()));
    fields.put("token_cache_read", DisplayFormatters.formatCompactToken(round.cacheReadTokens()));
    fields.put("token_cache_write", DisplayFormatters.formatCompactToken(round.cacheWriteTokens()));
    fields.put("token_output", DisplayFormatters.formatCompactToken(round.outputTokens()));
    double tokenBarPct = DisplayFormatters.percentValue(total, maxTokens);
    fields.put("token_bar_pct", tokenBarPct);
    fields.put(
        "token_bar_label",
        maxTokens > 0
            ? DisplayFormatters.percentLabel(total, maxTokens) + " of max round tokens"
            : "No round tokens");
    fields.put(
        "token_bar_gap_label",
        maxTokens > 0
            ? DisplayFormatters.percentLabel(Math.max(maxTokens - total, 0), maxTokens)
                + " below max round tokens"
            : "No round token gap");
    Map<String, Object> mix = new LinkedHashMap<>();
    mix.put("fresh", DisplayFormatters.percentValue(round.freshInputTokens(), total));
    mix.put("read", DisplayFormatters.percentValue(round.cacheReadTokens(), total));
    mix.put("write", DisplayFormatters.percentValue(round.cacheWriteTokens(), total));
    mix.put("out", DisplayFormatters.percentValue(round.outputTokens(), total));
    fields.put("token_mix", mix);
    fields.put("fresh_share", DisplayFormatters.percentLabel(round.freshInputTokens(), total));
    fields.put("cache_read_share", DisplayFormatters.percentLabel(round.cacheReadTokens(), total));
    fields.put(
        "cache_write_share", DisplayFormatters.percentLabel(round.cacheWriteTokens(), total));
    fields.put("output_share", DisplayFormatters.percentLabel(round.outputTokens(), total));
    fields.put("cache_read_ratio", roundCacheReadLabel(round));
    fields.put("bar_height_px", maxTokens > 0 ? tokenBarPct * 1.18 : 0.0);
    return fields;
  }

  private static boolean hasAgentTool(List<String> toolCallIds) {
    for (String toolCallId : toolCallIds) {
      if (toolCallId != null && toolCallId.toLowerCase().contains("agent")) {
        return true;
      }
    }
    return false;
  }

  private static String firstSubagentId(List<String> callIds) {
    for (String callId : callIds) {
      int marker = callId.indexOf("-SR");
      if (marker > 0) {
        return callId.substring(0, marker);
      }
    }
    return "";
  }

  private static String firstSubagentRound(List<String> callIds, String subagentId) {
    String prefix = subagentId + "-SR";
    for (String callId : callIds) {
      if (callId.startsWith(prefix)) {
        return callId.substring(prefix.length());
      }
    }
    return "1";
  }

  private static boolean hasSubagentRounds(List<Map<String, Object>> rounds) {
    for (Map<String, Object> round : rounds) {
      Object subagentId = round.get("subagent_id");
      if (subagentId instanceof String value && !value.isEmpty()) {
        return true;
      }
    }
    return false;
  }

  private static boolean hasTokenUsage(List<Map<String, Object>> rounds, boolean subagentOnly) {
    for (Map<String, Object> round : rounds) {
      Object subagent = round.get("subagent_id");
      Object usage = round.get("has_token_usage");
      boolean hasSubagent = subagent instanceof String id && !id.isEmpty();
      if ((!subagentOnly || hasSubagent) && usage instanceof Boolean hasUsage && hasUsage) {
        return true;
      }
    }
    return false;
  }

  private static String primarySubagentId(List<Map<String, Object>> rounds) {
    for (Map<String, Object> round : rounds) {
      Object subagentId = round.get("subagent_id");
      if (subagentId instanceof String value && !value.isEmpty()) {
        return value;
      }
    }
    return "";
  }

  /**
   * 构建 payload 来源摘要列表。
   *
   * <p>只包含元信息（ID、类型、状态），不包含实际 payload 内容。 敏感 payload 默认隐藏。
   *
   * @param sources payload 来源列表
   * @return 展示用 payload 来源摘要列表
   */
  private static List<Map<String, String>> buildPayloadSourceSummary(List<PayloadSource> sources) {
    List<Map<String, String>> result = new ArrayList<>(sources.size());
    for (PayloadSource source : sources) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("payload_id", source.payloadId());
      entry.put("kind", source.kind().name().toLowerCase());
      entry.put("call_id", source.callId());
      entry.put("title", source.title());
      entry.put("truncated", source.truncated() ? "true" : "false");
      entry.put("status", source.truncated() ? "truncated" : "available");
      result.add(entry);
    }
    return result;
  }

  private static String primaryPayloadId(List<PayloadSource> payloadSources) {
    return payloadSources.isEmpty() ? "" : payloadSources.get(0).payloadId();
  }

  /**
   * 构建 session 指标 map，供 hero 区域展示。
   *
   * @param row 会话行数据
   * @return 指标 map
   */
  private static Map<String, Object> buildSessionMetrics(
      SessionRow row, List<CallRound> rounds, SessionAnomalySummary anomalies) {
    Map<String, Object> metrics = new LinkedHashMap<>();
    double activeSeconds = row.modelExecutionSeconds() + row.toolExecutionSeconds();
    double waitingSeconds = Math.max(row.durationSeconds() - activeSeconds, 0.0);
    long subagentCallCount = subagentCallCount(rounds);
    long mainCallCount = Math.max(rounds.size(), row.assistantMessageCount() - subagentCallCount);
    long issueRounds = Math.max(anomalies.anomalyCount(), row.failedToolCount() > 0 ? 1 : 0);

    metrics.put("total_tokens", row.totalTokens());
    metrics.put("output_tokens", row.outputTokens());
    metrics.put("fresh_input_tokens", row.freshInputTokens());
    metrics.put("cache_read_tokens", row.cacheReadTokens());
    metrics.put("cache_write_tokens", row.cacheWriteTokens());
    metrics.put("duration_seconds", row.durationSeconds());
    metrics.put("model_execution_seconds", row.modelExecutionSeconds());
    metrics.put("tool_execution_seconds", row.toolExecutionSeconds());
    metrics.put("tool_call_count", row.toolCallCount());
    metrics.put("failed_tool_count", row.failedToolCount());
    metrics.put("user_message_count", row.userMessageCount());
    metrics.put("assistant_message_count", row.assistantMessageCount());
    metrics.put("subagent_instance_count", row.subagentInstanceCount());
    metrics.put("tokens", DisplayFormatters.formatCompactToken(row.totalTokens()));
    metrics.put("tokens_note", "Fresh + Cache Read + Cache Write + Output");
    metrics.put("fresh", DisplayFormatters.formatCompactToken(row.freshInputTokens()));
    metrics.put("cache_read", DisplayFormatters.formatCompactToken(row.cacheReadTokens()));
    metrics.put("cache_write", DisplayFormatters.formatCompactToken(row.cacheWriteTokens()));
    metrics.put("output", DisplayFormatters.formatCompactToken(row.outputTokens()));
    metrics.put(
        "fresh_share", DisplayFormatters.percentLabel(row.freshInputTokens(), row.totalTokens()));
    metrics.put(
        "cache_read_share",
        DisplayFormatters.percentLabel(row.cacheReadTokens(), row.totalTokens()));
    metrics.put(
        "cache_write_share",
        DisplayFormatters.percentLabel(row.cacheWriteTokens(), row.totalTokens()));
    metrics.put(
        "output_share", DisplayFormatters.percentLabel(row.outputTokens(), row.totalTokens()));
    metrics.put("fresh_share_tone", shareTone(row.freshInputTokens(), row.totalTokens()));
    metrics.put("cache_read_share_tone", shareTone(row.cacheReadTokens(), row.totalTokens()));
    metrics.put("cache_write_share_tone", shareTone(row.cacheWriteTokens(), row.totalTokens()));
    metrics.put("output_share_tone", shareTone(row.outputTokens(), row.totalTokens()));
    metrics.put(
        "cache_reuse",
        DisplayFormatters.percentLabel(row.cacheReadTokens(), sessionInputSide(row)));
    metrics.put("input_side_tokens", DisplayFormatters.formatCompactToken(sessionInputSide(row)));
    metrics.put("low_cache_rounds", lowCacheRoundCount(rounds));
    metrics.put("fresh_spike_rounds", freshSpikeRoundCount(rounds));
    metrics.put("run_health", issueRounds > 0 ? "Needs Review" : "Completed");
    metrics.put("issue_rounds", issueRounds);
    metrics.put("failed_tools", row.failedToolCount());
    metrics.put(
        "failed_tools_rate",
        DisplayFormatters.percentLabel(row.failedToolCount(), row.toolCallCount()));
    metrics.put("failed_tools_tone", row.failedToolCount() > 0 ? "bad" : "ok");
    metrics.put("payload_gaps", 0);
    metrics.put("attribution_gaps", 0);
    metrics.put("workload", row.assistantMessageCount() + " LLM");
    metrics.put("llm_calls", row.assistantMessageCount());
    metrics.put("main_llm_calls", mainCallCount);
    metrics.put("subagent_llm_calls", subagentCallCount);
    metrics.put("tool_calls", row.toolCallCount());
    metrics.put("subagent_runs", row.subagentInstanceCount());
    metrics.put("active_time", DisplayFormatters.formatDuration(activeSeconds));
    metrics.put("duration", DisplayFormatters.formatDuration(row.durationSeconds()));
    metrics.put("waiting_time", DisplayFormatters.formatDuration(waitingSeconds));
    metrics.put("process_time", DisplayFormatters.formatDuration(activeSeconds));
    metrics.put("model_time", DisplayFormatters.formatDuration(row.modelExecutionSeconds()));
    metrics.put("tool_time", DisplayFormatters.formatDuration(row.toolExecutionSeconds()));
    metrics.put("updated", DisplayFormatters.toLocalTime(row.endedAt()));
    return metrics;
  }

  private static long subagentCallCount(List<CallRound> rounds) {
    return rounds.stream()
        .filter(round -> !round.parentCallId().isEmpty())
        .mapToLong(CallRound::callCount)
        .sum();
  }

  private static long lowCacheRoundCount(List<CallRound> rounds) {
    return rounds.stream().filter(SessionDetailPage::isLowCacheRound).count();
  }

  private static boolean isLowCacheRound(CallRound round) {
    return roundInputSide(round) > 0 && roundCacheReadPercent(round) < 20.0;
  }

  private static long freshSpikeRoundCount(List<CallRound> rounds) {
    List<Long> freshValues = new ArrayList<>();
    for (CallRound round : rounds) {
      if (round.freshInputTokens() > 0) {
        freshValues.add(round.freshInputTokens());
      }
    }
    if (freshValues.isEmpty()) {
      return 0;
    }
    freshValues.sort(Long::compare);
    long median = freshValues.get(freshValues.size() / 2);
    if (median <= 0) {
      return 0;
    }
    return freshValues.stream().filter(value -> value > median * 2).count();
  }

  private static String shareTone(long numerator, long denominator) {
    double share = DisplayFormatters.percentValue(numerator, denominator);
    if (share >= 50.0) {
      return "major";
    }
    if (share >= 20.0) {
      return "mid";
    }
    return "minor";
  }

  private static long sessionInputSide(SessionRow row) {
    return row.freshInputTokens() + row.cacheReadTokens() + row.cacheWriteTokens();
  }

  private static long roundInputSide(CallRound round) {
    return round.freshInputTokens() + round.cacheReadTokens() + round.cacheWriteTokens();
  }

  private static double roundCacheReadPercent(CallRound round) {
    return DisplayFormatters.percentValue(round.cacheReadTokens(), roundInputSide(round));
  }

  private static String roundCacheReadLabel(CallRound round) {
    return DisplayFormatters.percentLabel(round.cacheReadTokens(), roundInputSide(round));
  }

  private static List<Map<String, Object>> buildContextSegments(SessionRow row) {
    long denominator = Math.max(1, sessionInputSide(row));
    List<Map<String, Object>> segments = new ArrayList<>();
    segments.add(
        contextSegment(
            1,
            "Fresh input",
            row.freshInputTokens(),
            denominator,
            "fresh",
            "Normalized call usage"));
    segments.add(
        contextSegment(
            2,
            "Cache read",
            row.cacheReadTokens(),
            denominator,
            "reused",
            "Provider/broker usage"));
    segments.add(
        contextSegment(
            3,
            "Cache write",
            row.cacheWriteTokens(),
            denominator,
            "write",
            "Provider/broker usage"));
    return segments;
  }

  private static Map<String, Object> contextSegment(
      int index, String label, long tokens, long denominator, String status, String source) {
    Map<String, Object> segment = new LinkedHashMap<>();
    double shareValue = DisplayFormatters.percentValue(tokens, denominator);
    segment.put("index", index);
    segment.put("label", label);
    segment.put("tokens", tokens);
    segment.put("tokens_label", DisplayFormatters.formatCompactToken(tokens));
    segment.put("share", String.format(java.util.Locale.ROOT, "%.1f%%", shareValue));
    segment.put("share_value", shareValue);
    segment.put("status", status);
    segment.put("source", source);
    segment.put("precision", "normalized");
    return segment;
  }

  /**
   * 构建 round 导航列表。
   *
   * <p>用于页面顶部 round 快速跳转。
   *
   * @param rounds 完整 round 列表
   * @return 导航列表，每项包含 idx、name、status
   */
  private static List<Map<String, Object>> buildRoundNavList(List<CallRound> rounds) {
    int limit = Math.min(rounds.size(), MAX_INITIAL_ROUNDS);
    List<Map<String, Object>> result = new ArrayList<>(limit);
    for (int i = 0; i < limit; i++) {
      CallRound round = rounds.get(i);
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put("idx", round.roundIndex());
      entry.put("name", "Round " + round.roundIndex());
      entry.put("call_count", round.callCount());
      entry.put("is_subagent", !round.parentCallId().isEmpty());
      result.add(entry);
    }
    return result;
  }

  /**
   * 将异常严重度映射为 UI tone 标识。
   *
   * @param severity 异常严重度
   * @return tone 字符串
   */
  private static String severityTone(AnomalySeverity severity) {
    return severity.getValue();
  }

  /**
   * URL 编码字符串。
   *
   * @param value 待编码值
   * @return URL 编码后的字符串
   */
  private static String urlEncode(String value) {
    return java.net.URLEncoder.encode(value, StandardCharsets.UTF_8);
  }

  /**
   * 截断字符串用于显示。
   *
   * @param value 原始值
   * @param maxLen 最大长度
   * @return 截断后的字符串
   */
  private static String truncateForDisplay(String value, int maxLen) {
    if (value == null || value.length() <= maxLen) {
      return value != null ? value : "";
    }
    return value.substring(0, maxLen) + "...";
  }
}
