package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 类型化 payload 来源引用。
 *
 * <p>标识会话详情中可展开的 payload 内容位置，对应 Python {@code _build_payload_lookup} 生成的 payload_id。 每个 payload
 * source 唯一标识一个请求、响应或工具结果内容块。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code payloadId} 不得为 null 或空字符串。
 *   <li>{@code kind} 不得为 null。
 *   <li>{@code callId} 不得为 null 或空字符串。
 * </ul>
 *
 * @param payloadId 全局唯一的 payload 标识符，用于 lookup 查询
 * @param kind payload 类型分类
 * @param callId 关联的归一化调用 ID
 * @param title 显示标题，缺失时为空字符串
 * @param truncated 内容是否被截断（标准可见性下为 true）
 */
public record PayloadSource(
    String payloadId, PayloadSourceKind kind, String callId, String title, boolean truncated) {

  /**
   * 紧凑构造器，验证 payload 来源不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当标识字段为空字符串时
   */
  public PayloadSource {
    Objects.requireNonNull(payloadId, "payloadId 不得为 null");
    if (payloadId.isEmpty()) {
      throw new IllegalArgumentException("payloadId 不得为空字符串");
    }
    Objects.requireNonNull(kind, "kind 不得为 null");
    Objects.requireNonNull(callId, "callId 不得为 null");
    if (callId.isEmpty()) {
      throw new IllegalArgumentException("callId 不得为空字符串");
    }
    title = title == null ? "" : title;
  }

  /**
   * 创建非截断的完整 payload 来源。
   *
   * @param payloadId payload 标识符
   * @param kind payload 类型
   * @param callId 关联调用 ID
   * @return 完整内容的 payload 来源
   */
  public static PayloadSource full(String payloadId, PayloadSourceKind kind, String callId) {
    return new PayloadSource(payloadId, kind, callId, "", false);
  }
}
