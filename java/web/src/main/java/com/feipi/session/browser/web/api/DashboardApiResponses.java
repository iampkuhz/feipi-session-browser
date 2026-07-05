package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** Dashboard resource APIs 的类型化 JSON 响应。 */
public final class DashboardApiResponses {

  private DashboardApiResponses() {}

  /**
   * 表示 DashboardFilterEcho 数据。
   *
   * @param agent agent 类型标识。
   * @param grain 趋势聚合粒度。
   * @param days 趋势覆盖天数。
   */
  public record DashboardFilterEcho(String agent, String grain, int days) {

    /** 校验字段和业务不变量。 */
    public DashboardFilterEcho {
      agent = ApiResponses.empty(agent);
      grain = ApiResponses.empty(grain);
      if (days < 1) {
        throw new IllegalArgumentException("days must be >= 1; got " + days);
      }
    }
  }

  /**
   * 表示 AgentCounts 数据。
   *
   * @param claudeCode Claude Code 指标值。
   * @param codex Codex 指标值。
   * @param qoder Qoder 指标值。
   * @param total 汇总数量。
   */
  public record AgentCounts(long claudeCode, long codex, long qoder, long total) {

    /** 校验字段和业务不变量。 */
    public AgentCounts {
      if (claudeCode < 0 || codex < 0 || qoder < 0 || total < 0) {
        throw new IllegalArgumentException("agent counts must be non-negative");
      }
      if (claudeCode + codex + qoder > total) {
        throw new IllegalArgumentException("agent counts must not exceed total");
      }
    }
  }

  /**
   * 表示 RatioDto 数据。
   *
   * @param value 字段原始值。
   * @param reason 不可用原因。
   */
  public record RatioDto(Double value, String reason) {

    /** 校验字段和业务不变量。 */
    public RatioDto {
      reason = reason == null ? "" : reason;
      if (value != null && (value < 0.0 || value > 1.0)) {
        throw new IllegalArgumentException("ratio value must be between 0 and 1");
      }
    }

    /** 创建可用比例值。 */
    public static RatioDto of(Double value) {
      return new RatioDto(value, value == null ? "no_eligible_input_tokens" : "");
    }
  }

  /**
   * 表示 DashboardSummaryResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param sessionCount 当前过滤条件下的 session 数量。
   * @param projectCount 当前过滤条件下的项目数量。
   * @param agents 该字段在 API 响应中的业务值。
   * @param tokens token 组成统计。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param userMessages 当前统计口径下的消息数量。
   * @param assistantMessages 当前统计口径下的消息数量。
   * @param cacheReadRatio 当前统计口径下的指标值。
   * @param state 页面或 API 状态描述。
   */
  public record DashboardSummaryResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      long sessionCount,
      long projectCount,
      AgentCounts agents,
      TokenSegments tokens,
      long toolCalls,
      long failedTools,
      long userMessages,
      long assistantMessages,
      RatioDto cacheReadRatio,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public DashboardSummaryResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(agents, "agents must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      Objects.requireNonNull(cacheReadRatio, "cacheReadRatio must not be null");
      Objects.requireNonNull(state, "state must not be null");
      if (sessionCount < 0
          || projectCount < 0
          || toolCalls < 0
          || failedTools < 0
          || userMessages < 0
          || assistantMessages < 0) {
        throw new IllegalArgumentException("summary counts must be non-negative");
      }
    }
  }

  /**
   * 表示 DashboardSessionsTrendResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rangeTotal 当前范围总数。
   * @param points 趋势点列表。
   * @param state 页面或 API 状态描述。
   */
  public record DashboardSessionsTrendResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      long rangeTotal,
      List<SessionTrendPoint> points,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public DashboardSessionsTrendResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(points, "points must not be null");
      Objects.requireNonNull(state, "state must not be null");
      points = List.copyOf(points);
      if (rangeTotal < 0) {
        throw new IllegalArgumentException("rangeTotal must be non-negative");
      }
    }
  }

  /**
   * 表示 SessionTrendPoint 数据。
   *
   * @param date 日期桶。
   * @param totalCount 汇总数量。
   * @param claudeCount Claude Code session 数量。
   * @param codexCount Codex session 数量。
   * @param qoderCount Qoder session 数量。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   */
  public record SessionTrendPoint(
      String date,
      long totalCount,
      long claudeCount,
      long codexCount,
      long qoderCount,
      long toolCalls,
      long failedTools) {

    /** 校验字段和业务不变量。 */
    public SessionTrendPoint {
      date = ApiResponses.required(date, "date");
      if (totalCount < 0
          || claudeCount < 0
          || codexCount < 0
          || qoderCount < 0
          || toolCalls < 0
          || failedTools < 0) {
        throw new IllegalArgumentException("trend counts must be non-negative");
      }
    }
  }

  /**
   * 表示 DashboardTokenTrendResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rangeTotals 当前范围 token 汇总。
   * @param points 趋势点列表。
   * @param state 页面或 API 状态描述。
   */
  public record DashboardTokenTrendResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      TokenSegments rangeTotals,
      List<TokenTrendPoint> points,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public DashboardTokenTrendResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rangeTotals, "rangeTotals must not be null");
      Objects.requireNonNull(points, "points must not be null");
      Objects.requireNonNull(state, "state must not be null");
      points = List.copyOf(points);
    }
  }

  /**
   * 表示 TokenTrendPoint 数据。
   *
   * @param date 日期桶。
   * @param tokens token 组成统计。
   * @param claudeTokens Claude Code token 数量。
   * @param codexTokens Codex token 数量。
   * @param qoderTokens Qoder token 数量。
   */
  public record TokenTrendPoint(
      String date, TokenSegments tokens, long claudeTokens, long codexTokens, long qoderTokens) {

    /** 校验字段和业务不变量。 */
    public TokenTrendPoint {
      date = ApiResponses.required(date, "date");
      Objects.requireNonNull(tokens, "tokens must not be null");
      if (claudeTokens < 0 || codexTokens < 0 || qoderTokens < 0) {
        throw new IllegalArgumentException("agent token totals must be non-negative");
      }
    }
  }

  /**
   * 表示 DashboardPromptTrendResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rangeTotalPrompts 当前范围 prompt 总数。
   * @param points 趋势点列表。
   * @param state 页面或 API 状态描述。
   */
  public record DashboardPromptTrendResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      long rangeTotalPrompts,
      List<PromptTrendPoint> points,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public DashboardPromptTrendResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(points, "points must not be null");
      Objects.requireNonNull(state, "state must not be null");
      points = List.copyOf(points);
      if (rangeTotalPrompts < 0) {
        throw new IllegalArgumentException("rangeTotalPrompts must be non-negative");
      }
    }
  }

  /**
   * 表示 PromptTrendPoint 数据。
   *
   * @param date 日期桶。
   * @param totalPrompts prompt 汇总数量。
   * @param claudePrompts Claude Code prompt 数量。
   * @param codexPrompts Codex prompt 数量。
   * @param qoderPrompts Qoder prompt 数量。
   * @param assistantTurns 该字段在 API 响应中的业务值。
   * @param toolCalls 当前统计口径下的调用数量。
   */
  public record PromptTrendPoint(
      String date,
      long totalPrompts,
      long claudePrompts,
      long codexPrompts,
      long qoderPrompts,
      long assistantTurns,
      long toolCalls) {

    /** 校验字段和业务不变量。 */
    public PromptTrendPoint {
      date = ApiResponses.required(date, "date");
      if (totalPrompts < 0
          || claudePrompts < 0
          || codexPrompts < 0
          || qoderPrompts < 0
          || assistantTurns < 0
          || toolCalls < 0) {
        throw new IllegalArgumentException("prompt trend counts must be non-negative");
      }
    }
  }

  /**
   * 表示 DashboardCacheHealthResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param latestRatio 最新 cache 命中比例。
   * @param lowestRatio 最低 cache 命中比例。
   * @param points 趋势点列表。
   * @param state 页面或 API 状态描述。
   */
  public record DashboardCacheHealthResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      RatioDto latestRatio,
      RatioDto lowestRatio,
      List<CacheHealthPoint> points,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public DashboardCacheHealthResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(latestRatio, "latestRatio must not be null");
      Objects.requireNonNull(lowestRatio, "lowestRatio must not be null");
      Objects.requireNonNull(points, "points must not be null");
      Objects.requireNonNull(state, "state must not be null");
      points = List.copyOf(points);
    }
  }

  /**
   * 表示 CacheHealthPoint 数据。
   *
   * @param date 日期桶。
   * @param average 该字段在 API 响应中的业务值。
   * @param claudeCode Claude Code 指标值。
   * @param codex Codex 指标值。
   * @param qoder Qoder 指标值。
   */
  public record CacheHealthPoint(
      String date,
      CacheInputDto average,
      CacheInputDto claudeCode,
      CacheInputDto codex,
      CacheInputDto qoder) {

    /** 校验字段和业务不变量。 */
    public CacheHealthPoint {
      date = ApiResponses.required(date, "date");
      Objects.requireNonNull(average, "average must not be null");
      Objects.requireNonNull(claudeCode, "claudeCode must not be null");
      Objects.requireNonNull(codex, "codex must not be null");
      Objects.requireNonNull(qoder, "qoder must not be null");
    }
  }

  /**
   * 表示 CacheInputDto 数据。
   *
   * @param fresh fresh input token 数量。
   * @param cacheRead cache read token 数量。
   * @param cacheWrite cache write token 数量。
   * @param totalInput 输入侧 token 总量。
   * @param ratio 比例值。
   */
  public record CacheInputDto(
      long fresh, long cacheRead, long cacheWrite, long totalInput, RatioDto ratio) {

    /** 校验字段和业务不变量。 */
    public CacheInputDto {
      if (fresh < 0 || cacheRead < 0 || cacheWrite < 0 || totalInput < 0) {
        throw new IllegalArgumentException("cache input values must be non-negative");
      }
      if (totalInput != fresh + cacheRead + cacheWrite) {
        throw new IllegalArgumentException("totalInput must equal fresh + cacheRead + cacheWrite");
      }
      Objects.requireNonNull(ratio, "ratio must not be null");
    }

    /** 构建 cache input 元组并推导比例。 */
    public static CacheInputDto of(long fresh, long cacheRead, long cacheWrite) {
      long totalInput = fresh + cacheRead + cacheWrite;
      Double ratio = totalInput > 0 ? cacheRead / (double) totalInput : null;
      return new CacheInputDto(fresh, cacheRead, cacheWrite, totalInput, RatioDto.of(ratio));
    }
  }

  /**
   * 表示 AgentsContributionResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param totalSessions session 汇总数量。
   * @param totalTokens token 汇总数量。
   * @param totalPrompts prompt 汇总数量。
   * @param rows 结果行列表。
   * @param state 页面或 API 状态描述。
   */
  public record AgentsContributionResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      long totalSessions,
      TokenSegments totalTokens,
      long totalPrompts,
      List<AgentContributionDto> rows,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public AgentsContributionResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(totalTokens, "totalTokens must not be null");
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
      if (totalSessions < 0 || totalPrompts < 0) {
        throw new IllegalArgumentException("contribution totals must be non-negative");
      }
    }
  }

  /**
   * 表示 AgentContributionDto 数据。
   *
   * @param agent agent 类型标识。
   * @param label 用户可读标签。
   * @param sessionCount 当前过滤条件下的 session 数量。
   * @param tokens token 组成统计。
   * @param prompts 该字段在 API 响应中的业务值。
   * @param projectCount 当前过滤条件下的项目数量。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param sessionShare session 占比。
   * @param tokenShare token 占比。
   * @param promptShare prompt 占比。
   */
  public record AgentContributionDto(
      String agent,
      String label,
      long sessionCount,
      TokenSegments tokens,
      long prompts,
      long projectCount,
      long toolCalls,
      long failedTools,
      double sessionShare,
      double tokenShare,
      double promptShare) {

    /** 校验字段和业务不变量。 */
    public AgentContributionDto {
      agent = ApiResponses.required(agent, "agent");
      label = ApiResponses.empty(label);
      Objects.requireNonNull(tokens, "tokens must not be null");
      if (sessionCount < 0 || prompts < 0 || projectCount < 0 || toolCalls < 0 || failedTools < 0) {
        throw new IllegalArgumentException("contribution counts must be non-negative");
      }
    }
  }

  /**
   * 表示 AgentsEfficiencyResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rows 结果行列表。
   * @param state 页面或 API 状态描述。
   */
  public record AgentsEfficiencyResponse(
      String schemaVersion,
      DashboardFilterEcho filters,
      List<AgentEfficiencyDto> rows,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public AgentsEfficiencyResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
    }
  }

  /**
   * 表示 AgentEfficiencyDto 数据。
   *
   * @param agent agent 类型标识。
   * @param model 模型名称。
   * @param sessionCount 当前过滤条件下的 session 数量。
   * @param avgDurationSeconds 平均持续秒数。
   * @param p95DurationSeconds P95 持续秒数。
   * @param avgTokensPerSession 单 session 平均 token 数量。
   * @param avgToolsPerSession 单 session 平均工具数量。
   * @param toolsPerRound 单 round 工具数量。
   * @param cacheReuseRatio cache 复用比例。
   * @param failedPerSession 单 session 失败工具数量。
   */
  public record AgentEfficiencyDto(
      String agent,
      String model,
      long sessionCount,
      double avgDurationSeconds,
      double p95DurationSeconds,
      long avgTokensPerSession,
      double avgToolsPerSession,
      Double toolsPerRound,
      Double cacheReuseRatio,
      Double failedPerSession) {

    /** 校验字段和业务不变量。 */
    public AgentEfficiencyDto {
      agent = ApiResponses.required(agent, "agent");
      model = ApiResponses.required(model, "model");
      if (sessionCount < 0
          || avgDurationSeconds < 0
          || p95DurationSeconds < 0
          || avgTokensPerSession < 0
          || avgToolsPerSession < 0) {
        throw new IllegalArgumentException("efficiency values must be non-negative");
      }
    }
  }
}
