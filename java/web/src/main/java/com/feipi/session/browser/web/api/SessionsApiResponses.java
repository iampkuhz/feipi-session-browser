package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.api.PageApiDtos.SelectOptionDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** Sessions list resource APIs 的类型化 JSON 响应。 */
public final class SessionsApiResponses {

  private SessionsApiResponses() {}

  /**
   * 表示 SessionsFilterEcho 数据。
   *
   * @param agent agent 类型标识。
   * @param model 模型名称。
   * @param project 该字段在 API 响应中的业务值。
   * @param status 状态值。
   * @param q 该字段在 API 响应中的业务值。
   * @param sort 该字段在 API 响应中的业务值。
   * @param dir 该字段在 API 响应中的业务值。
   * @param page 当前页码。
   * @param pageSize 每页数量。
   */
  public record SessionsFilterEcho(
      String agent,
      String model,
      String project,
      String status,
      String q,
      String sort,
      String dir,
      int page,
      int pageSize) {

    /** 规范化输入字段并校验边界。 */
    public SessionsFilterEcho {
      agent = ApiResponses.empty(agent);
      model = ApiResponses.empty(model);
      project = ApiResponses.empty(project);
      status = ApiResponses.empty(status);
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
   * 表示 SessionsSummaryResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param totalCount 汇总数量。
   * @param projectCount 当前过滤条件下的项目数量。
   * @param tokens token 组成统计。
   * @param failedTools 当前统计口径下的工具数量。
   * @param state 页面或 API 状态描述。
   */
  public record SessionsSummaryResponse(
      String schemaVersion,
      SessionsFilterEcho filters,
      long totalCount,
      long projectCount,
      TokenSegments tokens,
      long failedTools,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionsSummaryResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      Objects.requireNonNull(state, "state must not be null");
      if (totalCount < 0 || projectCount < 0 || failedTools < 0) {
        throw new IllegalArgumentException("summary counts must be non-negative");
      }
    }
  }

  /**
   * 表示 SessionsOptionsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param agents 该字段在 API 响应中的业务值。
   * @param models 该字段在 API 响应中的业务值。
   * @param projects 该字段在 API 响应中的业务值。
   * @param statuses 该字段在 API 响应中的业务值。
   */
  public record SessionsOptionsResponse(
      String schemaVersion,
      SessionsFilterEcho filters,
      List<SelectOptionDto> agents,
      List<SelectOptionDto> models,
      List<SelectOptionDto> projects,
      List<SelectOptionDto> statuses) {

    /** 校验字段和业务不变量。 */
    public SessionsOptionsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(agents, "agents must not be null");
      Objects.requireNonNull(models, "models must not be null");
      Objects.requireNonNull(projects, "projects must not be null");
      Objects.requireNonNull(statuses, "statuses must not be null");
      agents = List.copyOf(agents);
      models = List.copyOf(models);
      projects = List.copyOf(projects);
      statuses = List.copyOf(statuses);
    }
  }

  /**
   * 表示 SessionsRowsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param rows 结果行列表。
   * @param pagination 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record SessionsRowsResponse(
      String schemaVersion,
      SessionsFilterEcho filters,
      List<SessionRowDto> rows,
      PaginationDto pagination,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionsRowsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rows, "rows must not be null");
      Objects.requireNonNull(pagination, "pagination must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rows = List.copyOf(rows);
    }
  }

  /**
   * 表示 SessionRowDto 数据。
   *
   * @param sessionKey 规范化 session key。
   * @param sessionId provider session 标识符。
   * @param title 会话标题。
   * @param projectKey 规范化 project key。
   * @param projectName 项目显示名称。
   * @param cwd 工作目录。
   * @param agent agent 类型标识。
   * @param model 模型名称。
   * @param tokens token 组成统计。
   * @param rounds round 列表。
   * @param tools 该字段在 API 响应中的业务值。
   * @param subagents 该字段在 API 响应中的业务值。
   * @param durationSeconds 持续时间秒数。
   * @param processSeconds 持续时间秒数。
   * @param failedTools 当前统计口径下的工具数量。
   * @param createdAt 时间戳。
   * @param updatedAt 时间戳。
   * @param detailUrl 该字段在 API 响应中的业务值。
   * @param projectUrl 该字段在 API 响应中的业务值。
   */
  public record SessionRowDto(
      String sessionKey,
      String sessionId,
      String title,
      String projectKey,
      String projectName,
      String cwd,
      String agent,
      String model,
      TokenSegments tokens,
      long rounds,
      long tools,
      long subagents,
      double durationSeconds,
      double processSeconds,
      long failedTools,
      String createdAt,
      String updatedAt,
      String detailUrl,
      String projectUrl) {

    /** 校验字段和业务不变量。 */
    public SessionRowDto {
      sessionKey = ApiResponses.required(sessionKey, "sessionKey");
      sessionId = ApiResponses.required(sessionId, "sessionId");
      title = ApiResponses.empty(title);
      projectKey = ApiResponses.empty(projectKey);
      projectName = ApiResponses.empty(projectName);
      cwd = ApiResponses.empty(cwd);
      agent = ApiResponses.required(agent, "agent");
      model = ApiResponses.empty(model);
      Objects.requireNonNull(tokens, "tokens must not be null");
      createdAt = ApiResponses.empty(createdAt);
      updatedAt = ApiResponses.empty(updatedAt);
      detailUrl = ApiResponses.empty(detailUrl);
      projectUrl = ApiResponses.empty(projectUrl);
      if (rounds < 0 || tools < 0 || subagents < 0 || failedTools < 0) {
        throw new IllegalArgumentException("row counts must be non-negative");
      }
      if (durationSeconds < 0 || processSeconds < 0) {
        throw new IllegalArgumentException("row durations must be non-negative");
      }
    }
  }
}
