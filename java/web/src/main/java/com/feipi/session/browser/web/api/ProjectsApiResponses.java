package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** Projects list resource APIs 的类型化 JSON 响应。 */
public final class ProjectsApiResponses {

  private ProjectsApiResponses() {}

  /**
   * 表示 ProjectsFilterEcho 数据。
   *
   * @param q 该字段在 API 响应中的业务值。
   * @param sort 该字段在 API 响应中的业务值。
   * @param dir 该字段在 API 响应中的业务值。
   * @param page 当前页码。
   * @param pageSize 每页数量。
   */
  public record ProjectsFilterEcho(String q, String sort, String dir, int page, int pageSize) {

    /** 规范化输入字段并校验边界。 */
    public ProjectsFilterEcho {
      q = ApiResponses.empty(q);
      sort = ApiResponses.empty(sort);
      dir = ApiResponses.empty(dir);
      if (page < 1) {
        throw new IllegalArgumentException("page must be >= 1; got " + page);
      }
      if (pageSize < 1) {
        throw new IllegalArgumentException("pageSize must be >= 1; got " + pageSize);
      }
    }
  }

  /**
   * 表示 ProjectsSummaryResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param projectCount 当前过滤条件下的项目数量。
   * @param sessionCount 当前过滤条件下的 session 数量。
   * @param tokens token 组成统计。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectsSummaryResponse(
      String schemaVersion,
      ProjectsFilterEcho filters,
      long projectCount,
      long sessionCount,
      TokenSegments tokens,
      long toolCalls,
      long failedTools,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectsSummaryResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      Objects.requireNonNull(state, "state must not be null");
      if (projectCount < 0 || sessionCount < 0 || toolCalls < 0 || failedTools < 0) {
        throw new IllegalArgumentException("summary counts must be non-negative");
      }
    }
  }

  /**
   * 表示 ProjectsRowsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rows 结果行列表。
   * @param pagination 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record ProjectsRowsResponse(
      String schemaVersion,
      ProjectsFilterEcho filters,
      List<ProjectRowDto> rows,
      PaginationDto pagination,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ProjectsRowsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(pagination, "pagination must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
    }
  }

  /**
   * 表示 ProjectRowDto 数据。
   *
   * @param projectKey 规范化 project key。
   * @param projectName 项目显示名称。
   * @param totalSessions session 汇总数量。
   * @param claudeSessions 该字段在 API 响应中的业务值。
   * @param codexSessions 该字段在 API 响应中的业务值。
   * @param qoderSessions 该字段在 API 响应中的业务值。
   * @param agents 非零 session 的 agent badge 列表。
   * @param tokens token 组成统计。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param userMessages 当前统计口径下的消息数量。
   * @param assistantMessages 当前统计口径下的消息数量。
   * @param firstSeen 该字段在 API 响应中的业务值。
   * @param lastSeen 该字段在 API 响应中的业务值。
   * @param detailUrl 该字段在 API 响应中的业务值。
   */
  public record ProjectRowDto(
      String projectKey,
      String projectName,
      long totalSessions,
      long claudeSessions,
      long codexSessions,
      long qoderSessions,
      List<ProjectAgentBadgeDto> agents,
      TokenSegments tokens,
      long toolCalls,
      long failedTools,
      long userMessages,
      long assistantMessages,
      String firstSeen,
      String lastSeen,
      String detailUrl) {

    /** 校验字段和业务不变量。 */
    public ProjectRowDto {
      projectKey = ApiResponses.required(projectKey, "projectKey");
      projectName = ApiResponses.empty(projectName);
      Objects.requireNonNull(agents, "agents must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      agents = List.copyOf(agents);
      firstSeen = ApiResponses.empty(firstSeen);
      lastSeen = ApiResponses.empty(lastSeen);
      detailUrl = ApiResponses.empty(detailUrl);
      if (totalSessions < 0
          || claudeSessions < 0
          || codexSessions < 0
          || qoderSessions < 0
          || toolCalls < 0
          || failedTools < 0
          || userMessages < 0
          || assistantMessages < 0) {
        throw new IllegalArgumentException("project row counts must be non-negative");
      }
      long agentSessions = claudeSessions + codexSessions + qoderSessions;
      if (agentSessions > totalSessions) {
        throw new IllegalArgumentException("agent session counts must not exceed totalSessions");
      }
    }
  }

  /**
   * 表示 ProjectAgentBadgeDto 数据。
   *
   * @param agent agent 类型标识。
   * @param label 用户可读标签。
   * @param sessions agent 在当前项目下的 session 数量。
   */
  public record ProjectAgentBadgeDto(String agent, String label, long sessions) {

    /** 校验字段和业务不变量。 */
    public ProjectAgentBadgeDto {
      agent = ApiResponses.required(agent, "agent");
      label = ApiResponses.empty(label);
      if (sessions < 0) {
        throw new IllegalArgumentException("agent sessions must be non-negative");
      }
    }
  }
}
