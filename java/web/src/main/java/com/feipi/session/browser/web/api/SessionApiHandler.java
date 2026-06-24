package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.sqlite.PayloadLookup;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.web.api.ApiResponses.ApiErrorResponse;
import com.feipi.session.browser.web.api.ApiResponses.AttributionData;
import com.feipi.session.browser.web.api.ApiResponses.AttributionResponse;
import com.feipi.session.browser.web.api.ApiResponses.BucketDetailResponse;
import com.feipi.session.browser.web.api.ApiResponses.CallSummary;
import com.feipi.session.browser.web.api.ApiResponses.CallUsage;
import com.feipi.session.browser.web.api.ApiResponses.PayloadNotFoundResponse;
import com.feipi.session.browser.web.api.ApiResponses.PayloadResponse;
import com.feipi.session.browser.web.api.ApiResponses.RoundResponse;
import com.feipi.session.browser.web.api.ApiResponses.RoundSummary;
import com.feipi.session.browser.web.api.SessionApiService.SessionApiContext;
import com.feipi.session.browser.web.api.SessionApiService.SessionDataException;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * JSON API 端点路由处理器。
 *
 * <p>处理所有 {@code /api/sessions/{agent}/{sessionId}/*} 请求：payload、round、attribution 和 bucket-detail
 * API。 每个端点使用 typed request/response，无 {@code Map} 响应。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>路径参数（agent、sessionId、roundIndex 等）在路由层解析并校验一次。
 *   <li>use case 信任已验证的 typed request。
 *   <li>数据库约束和 domain 不变量不在本层重复校验。
 * </ul>
 *
 * <p>统一错误 envelope：{@code {"error": "<code>", "message": "<description>"}}, HTTP status 决定错误类别。
 */
public final class SessionApiHandler {

  private static final Logger LOG = LoggerFactory.getLogger(SessionApiHandler.class);

  private final SessionApiService apiService;

  /**
   * 创建 API 处理器。
   *
   * @param apiService 会话 API 数据服务
   */
  public SessionApiHandler(SessionApiService apiService) {
    this.apiService = Objects.requireNonNull(apiService, "apiService 不得为 null");
  }

  /**
   * 处理 payload API。
   *
   * <p>返回指定 payload_id 的内容。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param payloadId payload 标识符
   */
  public void handlePayload(Context ctx, String agent, String sessionId, String payloadId) {
    if (payloadId.isBlank()) {
      sendError(ctx, HttpStatus.BAD_REQUEST, "bad_request", "payload_id 不得为空");
      return;
    }

    executeWithExceptionHandling(
        ctx,
        agent,
        sessionId,
        "payload",
        () -> {
          Optional<SessionApiContext> ctxOpt = loadContext(agent, sessionId);
          if (ctxOpt.isEmpty()) {
            sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
            return;
          }

          SessionApiContext sessionCtx = ctxOpt.get();
          PayloadLookup lookup = sessionCtx.payloadLookup();
          Optional<PayloadLookup.PayloadEntry> entryOpt = lookup.lookup(payloadId);

          if (entryOpt.isEmpty()) {
            List<String> availableIds = lookup.allPayloadIds();
            List<String> sample = availableIds.subList(0, Math.min(availableIds.size(), 10));
            ctx.status(HttpStatus.NOT_FOUND);
            ctx.json(
                new PayloadNotFoundResponse(
                    "not_found", "payload " + payloadId + " not found", sample));
            return;
          }

          PayloadLookup.PayloadEntry entry = entryOpt.get();
          ctx.json(
              new PayloadResponse(
                  entry.payloadId(),
                  entry.kind().name().toLowerCase(),
                  entry.callId(),
                  entry.content(),
                  entry.truncated(),
                  ApiResponses.SCHEMA_VERSION));
        });
  }

  /**
   * 处理 round lazy-load API。
   *
   * <p>返回指定轮次的结构化摘要数据。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param roundIndex 轮次序号（1-based，已由路由层校验）
   */
  public void handleRound(Context ctx, String agent, String sessionId, int roundIndex) {
    executeWithExceptionHandling(
        ctx,
        agent,
        sessionId,
        "round",
        () -> {
          Optional<SessionApiContext> ctxOpt = loadContext(agent, sessionId);
          if (ctxOpt.isEmpty()) {
            sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
            return;
          }

          SessionApiContext sessionCtx = ctxOpt.get();
          Optional<CallRound> roundOpt = sessionCtx.findRound(roundIndex);

          if (roundOpt.isEmpty()) {
            sendError(
                ctx,
                HttpStatus.NOT_FOUND,
                "not_found",
                "round_index "
                    + roundIndex
                    + " out of range (1-"
                    + sessionCtx.rounds().size()
                    + ")");
            return;
          }

          CallRound round = roundOpt.get();
          List<NormalizedCall> roundCalls = sessionCtx.callsInRound(round);
          RoundSummary summary = buildRoundSummary(round, roundCalls, sessionCtx);

          ctx.json(new RoundResponse(roundIndex, summary, ApiResponses.SCHEMA_VERSION));
        });
  }

  /**
   * 处理 main agent attribution API。
   *
   * <p>返回指定调用的 token 归因信息。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param roundIndex 轮次序号（1-based，已由路由层校验）
   * @param callIndex 调用序号（1-based，已由路由层校验）
   * @param kind 归因类型（request / response）
   */
  public void handleAttribution(
      Context ctx, String agent, String sessionId, int roundIndex, int callIndex, String kind) {
    if (!"request".equals(kind) && !"response".equals(kind)) {
      sendError(
          ctx,
          HttpStatus.BAD_REQUEST,
          "bad_request",
          "invalid kind '" + kind + "', expected 'request' or 'response'");
      return;
    }

    executeWithExceptionHandling(
        ctx,
        agent,
        sessionId,
        "attribution",
        () -> {
          Optional<SessionApiContext> ctxOpt = loadContext(agent, sessionId);
          if (ctxOpt.isEmpty()) {
            sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
            return;
          }

          SessionApiContext sessionCtx = ctxOpt.get();
          Optional<CallRound> roundOpt = sessionCtx.findRound(roundIndex);

          if (roundOpt.isEmpty()) {
            sendError(
                ctx,
                HttpStatus.NOT_FOUND,
                "not_found",
                "round_index "
                    + roundIndex
                    + " out of range (1-"
                    + sessionCtx.rounds().size()
                    + ")");
            return;
          }

          CallRound round = roundOpt.get();
          List<NormalizedCall> roundCalls = sessionCtx.callsInRound(round);

          if (callIndex > roundCalls.size()) {
            sendError(
                ctx,
                HttpStatus.NOT_FOUND,
                "not_found",
                "call_index "
                    + callIndex
                    + " out of range for round "
                    + roundIndex
                    + " (1-"
                    + roundCalls.size()
                    + ")");
            return;
          }

          NormalizedCall call = roundCalls.get(callIndex - 1);
          AttributionResponse response =
              buildAttributionResponse(agent, sessionId, roundIndex, callIndex, kind, call);
          ctx.json(response);
        });
  }

  /**
   * 处理 subagent attribution API。
   *
   * <p>返回指定子 agent 调用的 token 归因信息。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param subagentId 子 agent 标识
   * @param callIndex 调用序号（1-based，已由路由层校验）
   * @param kind 归因类型（request / response）
   */
  public void handleSubagentAttribution(
      Context ctx, String agent, String sessionId, String subagentId, int callIndex, String kind) {
    if (!"request".equals(kind) && !"response".equals(kind)) {
      sendError(
          ctx,
          HttpStatus.BAD_REQUEST,
          "bad_request",
          "invalid kind '" + kind + "', expected 'request' or 'response'");
      return;
    }

    executeWithExceptionHandling(
        ctx,
        agent,
        sessionId,
        "subagent attribution",
        () -> {
          Optional<SessionApiContext> ctxOpt = loadContext(agent, sessionId);
          if (ctxOpt.isEmpty()) {
            sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
            return;
          }

          SessionApiContext sessionCtx = ctxOpt.get();

          // 查找 subagent 调用
          List<NormalizedCall> subagentCalls =
              sessionCtx.calls().stream()
                  .filter(c -> c.scope() == CallScope.SUBAGENT)
                  .filter(c -> matchesSubagent(c, subagentId))
                  .toList();

          if (subagentCalls.isEmpty()) {
            sendError(
                ctx, HttpStatus.NOT_FOUND, "not_found", "subagent '" + subagentId + "' not found");
            return;
          }

          if (callIndex > subagentCalls.size()) {
            sendError(
                ctx,
                HttpStatus.NOT_FOUND,
                "not_found",
                "call_index "
                    + callIndex
                    + " out of range for subagent '"
                    + subagentId
                    + "' (1-"
                    + subagentCalls.size()
                    + ")");
            return;
          }

          NormalizedCall call = subagentCalls.get(callIndex - 1);

          // 确定该调用所在的轮次
          int roundIndex = findRoundIndexForCall(sessionCtx, call);
          AttributionResponse response =
              buildAttributionResponse(agent, sessionId, roundIndex, callIndex, kind, call);
          ctx.json(response);
        });
  }

  /**
   * 处理 bucket-detail API。
   *
   * <p>返回指定 bucket 的详细内容。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识
   * @param sessionId 会话标识
   * @param roundIndex 轮次序号（1-based，已由路由层校验）
   * @param bucketKey bucket 标识符
   */
  public void handleBucketDetail(
      Context ctx, String agent, String sessionId, int roundIndex, String bucketKey) {
    if (bucketKey.isBlank()) {
      sendError(ctx, HttpStatus.BAD_REQUEST, "bad_request", "bucket_key 不得为空");
      return;
    }

    executeWithExceptionHandling(
        ctx,
        agent,
        sessionId,
        "bucket-detail",
        () -> {
          Optional<SessionApiContext> ctxOpt = loadContext(agent, sessionId);
          if (ctxOpt.isEmpty()) {
            sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
            return;
          }

          SessionApiContext sessionCtx = ctxOpt.get();
          Optional<CallRound> roundOpt = sessionCtx.findRound(roundIndex);

          if (roundOpt.isEmpty()) {
            sendError(
                ctx,
                HttpStatus.NOT_FOUND,
                "not_found",
                "round_index "
                    + roundIndex
                    + " out of range (1-"
                    + sessionCtx.rounds().size()
                    + ")");
            return;
          }

          // bucket-detail 内容需要完整的 session 解析数据，当前归一化模型不直接提供。
          // 返回结构化的元信息作为占位。
          ctx.json(new BucketDetailResponse("bucket_detail", bucketKey, roundIndex, "", 0));
        });
  }

  /** 构建轮次摘要。 */
  private static RoundSummary buildRoundSummary(
      CallRound round, List<NormalizedCall> roundCalls, SessionApiContext sessionCtx) {
    List<CallSummary> callSummaries = new ArrayList<>(roundCalls.size());
    long totalTokens = 0;

    for (NormalizedCall call : roundCalls) {
      NormalizedCallUsage usage = call.usage();
      totalTokens += usage.total();
      callSummaries.add(
          new CallSummary(
              call.callId(),
              call.callKey(),
              call.model(),
              new CallUsage(
                  usage.fresh(),
                  usage.cacheRead(),
                  usage.cacheWrite(),
                  usage.output(),
                  usage.total()),
              call.scope().name().toLowerCase(),
              call.request().toolResultIds(),
              call.response().toolCallIds()));
    }

    // 查找该轮次关联的工具执行
    List<String> toolExecIds = findToolExecutionsForRound(round, sessionCtx);

    boolean isSubagent = !round.parentCallId().isEmpty();

    return new RoundSummary(
        round.calls(), toolExecIds, callSummaries, totalTokens, isSubagent, round.parentCallId());
  }

  /** 查找轮次关联的工具执行 ID。 */
  private static List<String> findToolExecutionsForRound(
      CallRound round, SessionApiContext sessionCtx) {
    List<NormalizedToolExecution> allToolExecs = sessionCtx.toolExecutions();
    List<String> result = new ArrayList<>();
    for (String callId : round.calls()) {
      for (NormalizedToolExecution exec : allToolExecs) {
        if (callId.equals(exec.declaredByCallId())) {
          result.add(exec.toolCallId());
        }
      }
    }
    return result;
  }

  /** 构建 attribution 响应。 */
  private static AttributionResponse buildAttributionResponse(
      String agent,
      String sessionId,
      int roundIndex,
      int callIndex,
      String kind,
      NormalizedCall call) {
    NormalizedCallUsage usage = call.usage();
    String attributionKind = "llm." + kind + "_attribution";

    AttributionData data =
        new AttributionData(
            call.model(),
            call.scope().name().toLowerCase(),
            usage.total(),
            usage.fresh(),
            usage.output(),
            usage.cacheRead(),
            usage.cacheWrite(),
            call.request().toolResultIds().size(),
            call.response().toolCallIds().size());

    return new AttributionResponse(attributionKind, agent, sessionId, roundIndex, callIndex, data);
  }

  /** 判断调用是否匹配指定的 subagent ID。 */
  private static boolean matchesSubagent(NormalizedCall call, String subagentId) {
    // 通过 parentCallId 匹配
    return call.parentCallId().map(parentId -> parentId.equals(subagentId)).orElse(false);
  }

  /** 查找调用所在的轮次序号。 */
  private static int findRoundIndexForCall(SessionApiContext sessionCtx, NormalizedCall call) {
    for (CallRound round : sessionCtx.rounds()) {
      if (round.calls().contains(call.callId())) {
        return round.roundIndex();
      }
    }
    return 1;
  }

  /** 加载会话上下文，统一处理异常。 */
  private Optional<SessionApiContext> loadContext(String agent, String sessionId)
      throws SQLException {
    String sessionKey = agent + ":" + sessionId;
    return apiService.getContext(sessionKey, PayloadVisibility.STANDARD);
  }

  /** 发送统一错误响应。 */
  private static void sendError(Context ctx, HttpStatus status, String error, String message) {
    ctx.status(status);
    ctx.json(new ApiErrorResponse(error, message));
  }

  /**
   * 执行 API 端点逻辑，统一处理制品异常和数据库异常。
   *
   * <p>将各端点重复的 try-catch 模式提取到此处，保证错误日志和响应 envelope 一致。
   *
   * @param ctx Javalin 请求上下文
   * @param agent agent 标识，用于日志
   * @param sessionId 会话标识，用于日志
   * @param endpointName 端点名称，用于日志
   * @param action 端点业务逻辑
   */
  private void executeWithExceptionHandling(
      Context ctx, String agent, String sessionId, String endpointName, ApiEndpointAction action) {
    try {
      action.execute();
    } catch (SessionDataException e) {
      LOG.error("{} API 制品加载失败: {}:{}", endpointName, agent, sessionId, e);
      sendError(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "artifact_error", "归一化制品加载失败");
    } catch (SQLException e) {
      LOG.error("{} API 查询失败: {}:{}", endpointName, agent, sessionId, e);
      sendError(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "internal_error", "查询失败");
    }
  }

  /** API 端点业务逻辑函数接口，允许抛出制品异常和数据库异常。 */
  @FunctionalInterface
  private interface ApiEndpointAction {

    /**
     * 执行端点逻辑。
     *
     * @throws SQLException 数据库查询失败
     * @throws SessionDataException 制品加载失败
     */
    void execute() throws SQLException, SessionDataException;
  }
}
