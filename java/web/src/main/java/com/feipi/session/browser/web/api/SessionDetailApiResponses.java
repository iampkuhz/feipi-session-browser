package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** Session Detail page resource APIs 的类型化 JSON 响应。 */
public final class SessionDetailApiResponses {

  private SessionDetailApiResponses() {}

  /**
   * 表示 SessionDetailFilterEcho 数据。
   *
   * @param agent agent 类型标识。
   * @param sessionId provider session 标识符。
   * @param visibility 导出可见性策略。
   */
  public record SessionDetailFilterEcho(String agent, String sessionId, String visibility) {

    /** 规范化输入字段并校验边界。 */
    public SessionDetailFilterEcho {
      agent = ApiResponses.required(agent, "agent");
      sessionId = ApiResponses.required(sessionId, "sessionId");
      visibility = ApiResponses.required(visibility, "visibility");
    }
  }

  /**
   * 表示 SessionMetaResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param sessionKey 规范化 session key。
   * @param title 会话标题。
   * @param projectKey 规范化 project key。
   * @param projectName 项目显示名称。
   * @param cwd 工作目录。
   * @param model 模型名称。
   * @param createdAt 时间戳。
   * @param updatedAt 时间戳。
   * @param gitBranch Git branch 名称。
   * @param source 该字段在 API 响应中的业务值。
   * @param hasArtifact 是否存在导出 artifact。
   * @param artifactSchemaVersion 该字段在 API 响应中的业务值。
   * @param cacheKey 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record SessionMetaResponse(
      String schemaVersion,
      SessionDetailFilterEcho filters,
      String sessionKey,
      String title,
      String projectKey,
      String projectName,
      String cwd,
      String model,
      String createdAt,
      String updatedAt,
      String gitBranch,
      String source,
      boolean hasArtifact,
      String artifactSchemaVersion,
      String cacheKey,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionMetaResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      sessionKey = ApiResponses.required(sessionKey, "sessionKey");
      title = ApiResponses.empty(title);
      projectKey = ApiResponses.empty(projectKey);
      projectName = ApiResponses.empty(projectName);
      cwd = ApiResponses.empty(cwd);
      model = ApiResponses.empty(model);
      createdAt = ApiResponses.empty(createdAt);
      updatedAt = ApiResponses.empty(updatedAt);
      gitBranch = ApiResponses.empty(gitBranch);
      source = ApiResponses.empty(source);
      artifactSchemaVersion = ApiResponses.empty(artifactSchemaVersion);
      cacheKey = ApiResponses.empty(cacheKey);
      Objects.requireNonNull(state, "state must not be null");
    }
  }

  /**
   * 表示 SessionMetricsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param tokens token 组成统计。
   * @param userMessages 当前统计口径下的消息数量。
   * @param assistantMessages 当前统计口径下的消息数量。
   * @param toolCalls 当前统计口径下的调用数量。
   * @param failedTools 当前统计口径下的工具数量。
   * @param subagents 该字段在 API 响应中的业务值。
   * @param durationSeconds 持续时间秒数。
   * @param modelExecutionSeconds 持续时间秒数。
   * @param toolExecutionSeconds 持续时间秒数。
   * @param roundCount round 数量。
   * @param payloadCount payload 数量。
   * @param state 页面或 API 状态描述。
   */
  public record SessionMetricsResponse(
      String schemaVersion,
      SessionDetailFilterEcho filters,
      TokenSegments tokens,
      long userMessages,
      long assistantMessages,
      long toolCalls,
      long failedTools,
      long subagents,
      double durationSeconds,
      double modelExecutionSeconds,
      double toolExecutionSeconds,
      long roundCount,
      long payloadCount,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionMetricsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      Objects.requireNonNull(state, "state must not be null");
      if (userMessages < 0
          || assistantMessages < 0
          || toolCalls < 0
          || failedTools < 0
          || subagents < 0
          || durationSeconds < 0
          || modelExecutionSeconds < 0
          || toolExecutionSeconds < 0
          || roundCount < 0
          || payloadCount < 0) {
        throw new IllegalArgumentException("metric values must be non-negative");
      }
    }
  }

  /**
   * 表示 SessionDiagnosticsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param anomalyCount 异常数量。
   * @param maxSeverity 该字段在 API 响应中的业务值。
   * @param mainReason 该字段在 API 响应中的业务值。
   * @param anomalies 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record SessionDiagnosticsResponse(
      String schemaVersion,
      SessionDetailFilterEcho filters,
      int anomalyCount,
      String maxSeverity,
      String mainReason,
      List<AnomalyDto> anomalies,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionDiagnosticsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      maxSeverity = ApiResponses.empty(maxSeverity);
      mainReason = ApiResponses.empty(mainReason);
      Objects.requireNonNull(anomalies, "anomalies must not be null");
      Objects.requireNonNull(state, "state must not be null");
      anomalies = List.copyOf(anomalies);
      if (anomalyCount < 0) {
        throw new IllegalArgumentException("anomalyCount must be non-negative");
      }
    }
  }

  /**
   * 表示 AnomalyDto 数据。
   *
   * @param type 该字段在 API 响应中的业务值。
   * @param severity 严重级别。
   * @param reason 不可用原因。
   */
  public record AnomalyDto(String type, String severity, String reason) {

    /** 校验字段和业务不变量。 */
    public AnomalyDto {
      type = ApiResponses.required(type, "type");
      severity = ApiResponses.required(severity, "severity");
      reason = ApiResponses.empty(reason);
    }
  }

  /**
   * 表示 SessionRoundsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param roundCount round 数量。
   * @param rounds round 列表。
   * @param state 页面或 API 状态描述。
   */
  public record SessionRoundsResponse(
      String schemaVersion,
      SessionDetailFilterEcho filters,
      long roundCount,
      List<RoundIndexDto> rounds,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionRoundsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(rounds, "rounds must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rounds = List.copyOf(rounds);
      if (roundCount < 0) {
        throw new IllegalArgumentException("roundCount must be non-negative");
      }
    }
  }

  /**
   * 表示 RoundIndexDto 数据。
   *
   * @param roundIndex 该字段在 API 响应中的业务值。
   * @param calls 该字段在 API 响应中的业务值。
   * @param toolCallIds 该字段在 API 响应中的业务值。
   * @param parentCallId 父调用标识符。
   * @param tokens token 组成统计。
   * @param callCount 当前统计口径下的数量。
   * @param toolCallCount 工具调用数量。
   * @param tokenShare token 占比。
   */
  public record RoundIndexDto(
      int roundIndex,
      List<String> calls,
      List<String> toolCallIds,
      String parentCallId,
      TokenSegments tokens,
      int callCount,
      int toolCallCount,
      Double tokenShare) {

    /** 校验字段和业务不变量。 */
    public RoundIndexDto {
      if (roundIndex < 1 || callCount < 0 || toolCallCount < 0) {
        throw new IllegalArgumentException("round values out of range");
      }
      Objects.requireNonNull(calls, "calls must not be null");
      Objects.requireNonNull(toolCallIds, "toolCallIds must not be null");
      Objects.requireNonNull(tokens, "tokens must not be null");
      calls = List.copyOf(calls);
      toolCallIds = List.copyOf(toolCallIds);
      parentCallId = ApiResponses.empty(parentCallId);
      if (tokenShare != null && (tokenShare < 0.0 || tokenShare > 1.0)) {
        throw new IllegalArgumentException("tokenShare must be between 0 and 1");
      }
    }
  }

  /**
   * 表示 SessionPayloadsResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param filters 规范化后的过滤条件。
   * @param payloadCount payload 数量。
   * @param payloads payload 列表。
   * @param state 页面或 API 状态描述。
   */
  public record SessionPayloadsResponse(
      String schemaVersion,
      SessionDetailFilterEcho filters,
      long payloadCount,
      List<PayloadIndexDto> payloads,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public SessionPayloadsResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(filters, "filters must not be null");
      Objects.requireNonNull(payloads, "payloads must not be null");
      Objects.requireNonNull(state, "state must not be null");
      payloads = List.copyOf(payloads);
      if (payloadCount < 0) {
        throw new IllegalArgumentException("payloadCount must be non-negative");
      }
    }
  }

  /**
   * 表示 PayloadIndexDto 数据。
   *
   * @param payloadId 标识符。
   * @param kind 该字段在 API 响应中的业务值。
   * @param callId 调用标识符。
   * @param title 会话标题。
   * @param truncated 该字段在 API 响应中的业务值。
   */
  public record PayloadIndexDto(
      String payloadId, String kind, String callId, String title, boolean truncated) {

    /** 校验字段和业务不变量。 */
    public PayloadIndexDto {
      payloadId = ApiResponses.required(payloadId, "payloadId");
      kind = ApiResponses.required(kind, "kind");
      callId = ApiResponses.required(callId, "callId");
      title = ApiResponses.empty(title);
    }
  }
}
