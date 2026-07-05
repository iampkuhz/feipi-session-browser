package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** Project Detail resource APIs 的类型化 JSON 响应。 */
public final class ProjectDetailApiResponses {

  private ProjectDetailApiResponses() {}

  /**
   * 表示 ProjectDetailFilterEcho 数据。
   *
   * @param projectKey 规范化 project key。
   * @param grain 趋势聚合粒度。
   */
  public record ProjectDetailFilterEcho(String projectKey, String grain) {

    /** 规范化输入字段并校验边界。 */
    public ProjectDetailFilterEcho {
      projectKey = ApiResponses.required(projectKey, "projectKey");
      grain = ApiResponses.empty(grain);
    }
  }

  /**
   * 表示 ProjectDetailSummaryResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param projectName 项目显示名称。
   * @param totalSessions session 汇总数量。
   * @param claudeSessions 该字段在 API 响应中的业务值。
   * @param codexSessions 该字段在 API 响应中的业务值。
   * @param qoderSessions 该字段在 API 响应中的业务值。
   * @param tokens token 组成统计。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param userMessages 当前统计口径下的消息数量。
   * @param assistantMessages 当前统计口径下的消息数量。
   * @param firstSeen 该字段在 API 响应中的业务值。
   * @param lastSeen 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectDetailSummaryResponse(
      String schemaVersion,
      ProjectDetailFilterEcho filters,
      String projectName,
      long totalSessions,
      long claudeSessions,
      long codexSessions,
      long qoderSessions,
      TokenSegments tokens,
      long toolCalls,
      long failedTools,
      long userMessages,
      long assistantMessages,
      String firstSeen,
      String lastSeen,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectDetailSummaryResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      projectName = ApiResponses.empty(projectName);
      Objects.requireNonNull(tokens, "tokens must not be null");
      firstSeen = ApiResponses.empty(firstSeen);
      lastSeen = ApiResponses.empty(lastSeen);
      Objects.requireNonNull(state, "state must not be null");
      if (totalSessions < 0
          || claudeSessions < 0
          || codexSessions < 0
          || qoderSessions < 0
          || toolCalls < 0
          || failedTools < 0
          || userMessages < 0
          || assistantMessages < 0) {
        throw new IllegalArgumentException("project detail counts must be non-negative");
      }
    }
  }

  /**
   * 表示 ProjectTokenTrendResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rangeTotals 当前范围 token 汇总。
   * @param points 趋势点列表。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectTokenTrendResponse(
      String schemaVersion,
      ProjectDetailFilterEcho filters,
      TokenSegments rangeTotals,
      List<ProjectTokenTrendPoint> points,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectTokenTrendResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rangeTotals, "rangeTotals must not be null");
      Objects.requireNonNull(points, "points must not be null");
      Objects.requireNonNull(state, "state must not be null");
      points = List.copyOf(points);
    }
  }

  /**
   * 表示 ProjectTokenTrendPoint 数据。
   *
   * @param label 用户可读标签。
   * @param tokens token 组成统计。
   */
  public record ProjectTokenTrendPoint(String label, TokenSegments tokens) {

    /** 校验字段和业务不变量。 */
    public ProjectTokenTrendPoint {
      label = ApiResponses.required(label, "label");
      Objects.requireNonNull(tokens, "tokens must not be null");
    }
  }

  /**
   * 表示 ProjectAgentMixResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param totalSessions session 汇总数量。
   * @param totalTokens token 汇总数量。
   * @param rows 结果行列表。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectAgentMixResponse(
      String schemaVersion,
      ProjectDetailFilterEcho filters,
      long totalSessions,
      TokenSegments totalTokens,
      List<ProjectAgentMixRow> rows,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectAgentMixResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(totalTokens, "totalTokens must not be null");
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
      if (totalSessions < 0) {
        throw new IllegalArgumentException("totalSessions must be non-negative");
      }
    }
  }

  /**
   * 表示 ProjectAgentMixRow 数据。
   *
   * @param agent agent 类型标识。
   * @param label 用户可读标签。
   * @param sessions 该字段在 API 响应中的业务值。
   * @param tokens token 组成统计。
   * @param failedTools 当前统计口径下的工具数量。
   * @param sessionShare session 占比。
   * @param tokenShare token 占比。
   */
  public record ProjectAgentMixRow(
      String agent,
      String label,
      long sessions,
      TokenSegments tokens,
      long failedTools,
      double sessionShare,
      double tokenShare) {

    /** 校验字段和业务不变量。 */
    public ProjectAgentMixRow {
      agent = ApiResponses.required(agent, "agent");
      label = ApiResponses.empty(label);
      Objects.requireNonNull(tokens, "tokens must not be null");
      if (sessions < 0 || failedTools < 0) {
        throw new IllegalArgumentException("agent mix counts must be non-negative");
      }
    }
  }

  /**
   * 表示 ProjectToolHotspotsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param available 该字段在 API 响应中的业务值。
   * @param reason 不可用原因。
   * @param rows 结果行列表。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectToolHotspotsResponse(
      String schemaVersion,
      ProjectDetailFilterEcho filters,
      boolean available,
      String reason,
      List<ProjectToolHotspotRow> rows,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectToolHotspotsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      reason = ApiResponses.empty(reason);
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
    }
  }

  /**
   * 表示 ProjectToolHotspotRow 数据。
   *
   * @param toolName 该字段在 API 响应中的业务值。
   * @param calls 该字段在 API 响应中的业务值。
   * @param failedCalls 当前统计口径下的调用数量。
   */
  public record ProjectToolHotspotRow(String toolName, long calls, long failedCalls) {

    /** 校验字段和业务不变量。 */
    public ProjectToolHotspotRow {
      toolName = ApiResponses.required(toolName, "toolName");
      if (calls < 0 || failedCalls < 0) {
        throw new IllegalArgumentException("tool hotspot counts must be non-negative");
      }
    }
  }
}
