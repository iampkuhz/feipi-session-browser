package com.feipi.session.browser.web.api;

import java.util.List;
import java.util.Objects;

/**
 * JSON API 统一响应类型。
 *
 * <p>每个 API 端点使用独立的 record 类型作为 JSON 响应载体，避免 {@code Map<String, Object>} 响应。 JSON field order
 * 不作为语义契约，schema 版本通过 {@code schemaVersion} 字段标识。
 */
public final class ApiResponses {

  private ApiResponses() {}

  /**
   * payload API 响应。
   *
   * <p>返回指定 payload_id 的内容元信息。
   *
   * @param payloadId payload 标识符
   * @param kind payload 类型（llm_request / llm_response / subagent_request / subagent_response）
   * @param callId 关联的归一化调用 ID
   * @param content payload 内容，标准可见性下可能为空
   * @param truncated 内容是否被截断
   * @param schemaVersion 响应 schema 版本
   */
  public record PayloadResponse(
      String payloadId,
      String kind,
      String callId,
      String content,
      boolean truncated,
      String schemaVersion) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public PayloadResponse {
      Objects.requireNonNull(payloadId, "payloadId 不得为 null");
      Objects.requireNonNull(kind, "kind 不得为 null");
      Objects.requireNonNull(callId, "callId 不得为 null");
      content = content == null ? "" : content;
      schemaVersion = schemaVersion == null ? "" : schemaVersion;
    }
  }

  /**
   * round lazy-load API 响应。
   *
   * <p>返回指定轮次的结构化摘要数据，供前端展开详情。
   *
   * @param roundId 轮次序号（1-based）
   * @param round 轮次摘要
   * @param schemaVersion 响应 schema 版本
   */
  public record RoundResponse(int roundId, RoundSummary round, String schemaVersion) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public RoundResponse {
      Objects.requireNonNull(round, "round 不得为 null");
      schemaVersion = schemaVersion == null ? "" : schemaVersion;
    }
  }

  /**
   * 轮次摘要数据。
   *
   * @param callIds 本轮次包含的调用 ID 列表
   * @param toolCallIds 本轮次关联的工具调用 ID 列表
   * @param calls 本轮次每个调用的摘要
   * @param totalTokens 本轮次累计 token 用量
   * @param isSubagent 是否为子 agent 轮次
   * @param parentCallId 父调用 ID，主会话轮次为空
   */
  public record RoundSummary(
      List<String> callIds,
      List<String> toolCallIds,
      List<CallSummary> calls,
      long totalTokens,
      boolean isSubagent,
      String parentCallId) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当集合字段为 null 时
     */
    public RoundSummary {
      Objects.requireNonNull(callIds, "callIds 不得为 null");
      Objects.requireNonNull(toolCallIds, "toolCallIds 不得为 null");
      Objects.requireNonNull(calls, "calls 不得为 null");
      callIds = List.copyOf(callIds);
      toolCallIds = List.copyOf(toolCallIds);
      calls = List.copyOf(calls);
      parentCallId = parentCallId == null ? "" : parentCallId;
    }
  }

  /**
   * 调用摘要数据。
   *
   * @param callId 调用 ID
   * @param callKey 调用展示键
   * @param model 模型名称
   * @param usage 调用 token 用量
   * @param scope 调用作用域
   * @param requestToolResultIds 请求侧工具结果 ID 列表
   * @param responseToolCallIds 响应侧工具调用 ID 列表
   */
  public record CallSummary(
      String callId,
      String callKey,
      String model,
      CallUsage usage,
      String scope,
      List<String> requestToolResultIds,
      List<String> responseToolCallIds) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public CallSummary {
      Objects.requireNonNull(callId, "callId 不得为 null");
      Objects.requireNonNull(callKey, "callKey 不得为 null");
      Objects.requireNonNull(model, "model 不得为 null");
      Objects.requireNonNull(usage, "usage 不得为 null");
      Objects.requireNonNull(scope, "scope 不得为 null");
      Objects.requireNonNull(requestToolResultIds, "requestToolResultIds 不得为 null");
      Objects.requireNonNull(responseToolCallIds, "responseToolCallIds 不得为 null");
      requestToolResultIds = List.copyOf(requestToolResultIds);
      responseToolCallIds = List.copyOf(responseToolCallIds);
    }
  }

  /**
   * 调用 token 用量。
   *
   * @param fresh 非缓存输入 token
   * @param cacheRead 缓存读取 token
   * @param cacheWrite 缓存写入 token
   * @param output 输出 token
   * @param total 总 token
   */
  public record CallUsage(long fresh, long cacheRead, long cacheWrite, long output, long total) {}

  /**
   * attribution API 响应。
   *
   * <p>返回指定调用的 token 归因信息。
   *
   * @param kind 归因类型（llm.request_attribution / llm.response_attribution）
   * @param source 源 agent 标识
   * @param sessionId 会话标识
   * @param roundIndex 轮次序号（1-based）
   * @param callIndex 调用序号（1-based）
   * @param data 归因数据
   */
  public record AttributionResponse(
      String kind,
      String source,
      String sessionId,
      int roundIndex,
      int callIndex,
      AttributionData data) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AttributionResponse {
      Objects.requireNonNull(kind, "kind 不得为 null");
      Objects.requireNonNull(source, "source 不得为 null");
      Objects.requireNonNull(sessionId, "sessionId 不得为 null");
      Objects.requireNonNull(data, "data 不得为 null");
    }
  }

  /**
   * attribution 数据内容。
   *
   * @param model 模型名称
   * @param scope 调用作用域
   * @param totalTokens 总 token 用量
   * @param freshInputTokens 非缓存输入 token
   * @param outputTokens 输出 token
   * @param cacheReadTokens 缓存读取 token
   * @param cacheWriteTokens 缓存写入 token
   * @param requestToolResultCount 请求侧工具结果数量
   * @param responseToolCallCount 响应侧工具调用数量
   */
  public record AttributionData(
      String model,
      String scope,
      long totalTokens,
      long freshInputTokens,
      long outputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      int requestToolResultCount,
      int responseToolCallCount) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AttributionData {
      Objects.requireNonNull(model, "model 不得为 null");
      Objects.requireNonNull(scope, "scope 不得为 null");
    }
  }

  /**
   * bucket-detail API 响应。
   *
   * @param kind 响应类型（bucket_detail）
   * @param bucketKey 查询的 bucket 标识
   * @param roundIndex 轮次序号（1-based）
   * @param text bucket 内容文本
   * @param tokens 估算 token 数量
   */
  public record BucketDetailResponse(
      String kind, String bucketKey, int roundIndex, String text, long tokens) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public BucketDetailResponse {
      Objects.requireNonNull(kind, "kind 不得为 null");
      Objects.requireNonNull(bucketKey, "bucketKey 不得为 null");
      text = text == null ? "" : text;
    }
  }

  /**
   * 统一错误响应。
   *
   * <p>所有 API 错误使用此 envelope，HTTP status code 决定错误类别。
   *
   * @param error 错误码（bad_request / not_found / internal_error）
   * @param message 人类可读错误描述
   */
  public record ApiErrorResponse(String error, String message) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public ApiErrorResponse {
      Objects.requireNonNull(error, "error 不得为 null");
      Objects.requireNonNull(message, "message 不得为 null");
    }
  }

  /**
   * payload 未找到时的错误响应，包含可用 payload_id 列表。
   *
   * @param error 错误码
   * @param message 错误描述
   * @param availablePayloadIds 可用的 payload ID 列表（最多 10 个）
   */
  public record PayloadNotFoundResponse(
      String error, String message, List<String> availablePayloadIds) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public PayloadNotFoundResponse {
      Objects.requireNonNull(error, "error 不得为 null");
      Objects.requireNonNull(message, "message 不得为 null");
      Objects.requireNonNull(availablePayloadIds, "availablePayloadIds 不得为 null");
      availablePayloadIds = List.copyOf(availablePayloadIds);
    }
  }

  /** API 响应 schema 版本常量。 */
  public static final String SCHEMA_VERSION = "1";
}
