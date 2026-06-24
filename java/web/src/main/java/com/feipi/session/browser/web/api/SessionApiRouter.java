package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.ApiResponses.ApiErrorResponse;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * JSON API 路径路由器。
 *
 * <p>将 {@code /api/sessions/*} 的 URL 路径解析为具体的 API 端点调用。 对应 Python {@code _dispatch_api_path}
 * 的路径分发逻辑。
 *
 * <p>支持的路由模式：
 *
 * <ul>
 *   <li>{@code /api/sessions/{agent}/{session_id}/payload/{payload_id}}
 *   <li>{@code /api/sessions/{agent}/{session_id}/round/{round_index}}
 *   <li>{@code /api/sessions/{agent}/{session_id}/attribution/{round}/{call}/{kind}}
 *   <li>{@code /api/sessions/{agent}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}}
 *   <li>{@code /api/sessions/{agent}/{session_id}/bucket-detail/{round_index}/{bucket_key}}
 * </ul>
 *
 * <p>校验放置：路径段解析和类型转换（整数 parse）在此层完成， 具体业务校验由 {@link SessionApiHandler} 执行。
 */
public final class SessionApiRouter {

  private static final Logger LOG = LoggerFactory.getLogger(SessionApiRouter.class);

  /** /api/sessions 前缀段数：["", "api", "sessions"] = 3。 */
  private static final int API_PREFIX_PARTS = 3;

  /** payload 路径总段数：prefix + agent + sessionId + "payload" + payloadId = 7。 */
  private static final int PAYLOAD_PARTS = 7;

  /** round 路径总段数：prefix + agent + sessionId + "round" + roundIndex = 7。 */
  private static final int ROUND_PARTS = 7;

  /**
   * main attribution 路径总段数：prefix + agent + sessionId + "attribution" + round + call + kind = 9。
   */
  private static final int ATTRIBUTION_MAIN_PARTS = 9;

  /**
   * subagent attribution 路径总段数：prefix + agent + sessionId + "attribution" + "subagent" + saId +
   * callIdx + kind = 10。
   */
  private static final int ATTRIBUTION_SUBAGENT_PARTS = 10;

  /**
   * bucket-detail 路径总段数：prefix + agent + sessionId + "bucket-detail" + roundIndex + bucketKey = 8。
   */
  private static final int BUCKET_DETAIL_PARTS = 8;

  private final SessionApiHandler handler;

  /**
   * 创建 API 路由器。
   *
   * @param handler API 端点处理器
   */
  public SessionApiRouter(SessionApiHandler handler) {
    this.handler = Objects.requireNonNull(handler, "handler 不得为 null");
  }

  /**
   * 路由 API 请求。
   *
   * <p>解析路径段并分发到对应的 API 端点。路径参数在此层解码和类型转换， 非法路径返回 400。
   *
   * @param ctx Javalin 请求上下文
   */
  public void route(Context ctx) {
    String path = ctx.path();
    String[] parts = path.split("/", -1);

    // 最小长度校验：至少 prefix + agent + sessionId + resource = 6
    if (parts.length < API_PREFIX_PARTS + 3) {
      sendBadRequest(ctx, "invalid API path: insufficient path segments");
      return;
    }

    String agent = decode(parts[3]);
    String sessionId = decode(parts[4]);
    String resource = parts[5];

    try {
      switch (resource) {
        case "payload" -> routePayload(ctx, parts, agent, sessionId);
        case "round" -> routeRound(ctx, parts, agent, sessionId);
        case "attribution" -> routeAttribution(ctx, parts, agent, sessionId);
        case "bucket-detail" -> routeBucketDetail(ctx, parts, agent, sessionId);
        default -> sendBadRequest(ctx, "invalid API path: unknown resource '" + resource + "'");
      }
    } catch (NumberFormatException e) {
      sendBadRequest(ctx, "invalid numeric parameter: " + e.getMessage());
    }
  }

  /**
   * 路由 payload 请求。
   *
   * <p>路径格式：{@code /api/sessions/{agent}/{session_id}/payload/{payload_id}}
   */
  private void routePayload(Context ctx, String[] parts, String agent, String sessionId) {
    if (parts.length != PAYLOAD_PARTS) {
      sendBadRequest(
          ctx,
          "invalid API path, expected: /api/sessions/{agent}/{session_id}/payload/{payload_id}");
      return;
    }
    String payloadId = decode(parts[6]);
    handler.handlePayload(ctx, agent, sessionId, payloadId);
  }

  /**
   * 路由 round 请求。
   *
   * <p>路径格式：{@code /api/sessions/{agent}/{session_id}/round/{round_index}}
   */
  private void routeRound(Context ctx, String[] parts, String agent, String sessionId) {
    if (parts.length != ROUND_PARTS) {
      sendBadRequest(
          ctx,
          "invalid API path, expected: /api/sessions/{agent}/{session_id}/round/{round_index}");
      return;
    }
    int roundIndex = parsePositiveInt(parts[6], "round_index");
    handler.handleRound(ctx, agent, sessionId, roundIndex);
  }

  /**
   * 路由 attribution 请求。
   *
   * <p>支持两种模式：
   *
   * <ul>
   *   <li>Main: {@code /api/sessions/{agent}/{session_id}/attribution/{round}/{call}/{kind}}
   *   <li>Subagent: {@code
   *       /api/sessions/{agent}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}}
   * </ul>
   */
  private void routeAttribution(Context ctx, String[] parts, String agent, String sessionId) {
    // 检测 subagent 模式
    if (parts.length == ATTRIBUTION_SUBAGENT_PARTS && "subagent".equals(parts[6])) {
      String subagentId = decode(parts[7]);
      int callIndex = parsePositiveInt(parts[8], "call_index");
      String kind = decode(parts[9]);
      handler.handleSubagentAttribution(ctx, agent, sessionId, subagentId, callIndex, kind);
      return;
    }

    // Main attribution 模式
    if (parts.length == ATTRIBUTION_MAIN_PARTS) {
      int roundIndex = parsePositiveInt(parts[6], "round_index");
      int callIndex = parsePositiveInt(parts[7], "call_index");
      String kind = decode(parts[8]);
      handler.handleAttribution(ctx, agent, sessionId, roundIndex, callIndex, kind);
      return;
    }

    sendBadRequest(ctx, "invalid API path, expected attribution pattern");
  }

  /**
   * 路由 bucket-detail 请求。
   *
   * <p>路径格式：{@code /api/sessions/{agent}/{session_id}/bucket-detail/{round_index}/{bucket_key}}
   */
  private void routeBucketDetail(Context ctx, String[] parts, String agent, String sessionId) {
    if (parts.length != BUCKET_DETAIL_PARTS) {
      sendBadRequest(
          ctx,
          "invalid API path, expected: /api/sessions/{agent}/{session_id}/bucket-detail/{round_index}/{bucket_key}");
      return;
    }
    int roundIndex = parsePositiveInt(parts[6], "round_index");
    String bucketKey = decode(parts[7]);
    handler.handleBucketDetail(ctx, agent, sessionId, roundIndex, bucketKey);
  }

  /** URL 解码路径段。 */
  private static String decode(String value) {
    return URLDecoder.decode(value, StandardCharsets.UTF_8);
  }

  /**
   * 解析正整数路径段。
   *
   * @param value 路径段字符串
   * @param paramName 参数名称，用于错误消息
   * @return 正整数值
   * @throws NumberFormatException 当值不是正整数时
   */
  private static int parsePositiveInt(String value, String paramName) {
    int result;
    try {
      result = Integer.parseInt(value);
    } catch (NumberFormatException e) {
      NumberFormatException wrapped =
          new NumberFormatException(paramName + "='" + value + "', must be a positive integer");
      wrapped.initCause(e);
      throw wrapped;
    }
    if (result < 1) {
      throw new NumberFormatException(paramName + " must be a positive integer, got " + value);
    }
    return result;
  }

  /** 发送 400 错误响应。 */
  private static void sendBadRequest(Context ctx, String message) {
    LOG.debug("API 路由错误: {}", message);
    ctx.status(HttpStatus.BAD_REQUEST);
    ctx.json(new ApiErrorResponse("bad_request", message));
  }
}
