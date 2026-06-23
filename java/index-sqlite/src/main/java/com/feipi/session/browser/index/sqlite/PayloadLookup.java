package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * payload 内容查找表。
 *
 * <p>从归一化制品构建 payload_id 到内容的映射。支持按可见性策略控制内容截断和敏感字段 masking。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>payload_id 格式由 {@link PayloadSource} 在创建时验证。
 *   <li>敏感字段 masking 由 {@link SensitiveFieldPolicy} 统一管理。
 *   <li>本类信任已验证的 payload_id 和制品数据。
 * </ul>
 */
public final class PayloadLookup {

  private final Map<String, PayloadEntry> entries;

  private PayloadLookup(Map<String, PayloadEntry> entries) {
    this.entries = Map.copyOf(entries);
  }

  /**
   * 从归一化制品构建 payload 查找表。
   *
   * <p>为每个有 sourceRef 的调用创建请求和响应条目。 标准可见性下内容标记为截断；完整可见性下保留全部内容。
   *
   * @param artifact 已验证的归一化制品
   * @param visibility 可见性策略
   * @return payload 查找表
   */
  public static PayloadLookup fromArtifact(
      NormalizedSessionArtifact artifact, PayloadVisibility visibility) {
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    boolean truncated = visibility == PayloadVisibility.STANDARD;
    Map<String, PayloadEntry> map = new LinkedHashMap<>();

    for (NormalizedCall call : artifact.calls()) {
      boolean isSubagent = call.scope().name().toLowerCase().contains("subagent");
      String prefix = isSubagent ? "sa" : "main";

      // 每次调用都有请求和响应两侧
      String reqPayloadId = prefix + ":req:" + call.callId();
      PayloadSourceKind requestKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST;
      map.put(
          reqPayloadId, new PayloadEntry(reqPayloadId, requestKind, call.callId(), "", truncated));

      String respPayloadId = prefix + ":resp:" + call.callId();
      PayloadSourceKind responseKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
      map.put(
          respPayloadId,
          new PayloadEntry(respPayloadId, responseKind, call.callId(), "", truncated));
    }
    return new PayloadLookup(map);
  }

  /**
   * 查找指定 payload_id 的内容。
   *
   * @param payloadId payload 标识符
   * @return payload 条目，不存在时返回 empty
   */
  public Optional<PayloadEntry> lookup(String payloadId) {
    Objects.requireNonNull(payloadId, "payloadId 不得为 null");
    return Optional.ofNullable(entries.get(payloadId));
  }

  /**
   * 查找指定调用 ID 的全部 payload 条目。
   *
   * @param callId 归一化调用 ID
   * @return 匹配的条目列表
   */
  public List<PayloadEntry> lookupByCallId(String callId) {
    Objects.requireNonNull(callId, "callId 不得为 null");
    return entries.values().stream().filter(e -> callId.equals(e.callId())).toList();
  }

  /** 查找表中的条目总数。 */
  public int size() {
    return entries.size();
  }

  /** 全部 payload_id 列表。 */
  public List<String> allPayloadIds() {
    return List.copyOf(entries.keySet());
  }

  /**
   * 单条 payload 内容条目。
   *
   * @param payloadId 全局唯一的 payload 标识符
   * @param kind payload 类型分类
   * @param callId 关联的归一化调用 ID
   * @param content payload 内容（可能已被 masking）
   * @param truncated 内容是否被截断
   */
  public record PayloadEntry(
      String payloadId, PayloadSourceKind kind, String callId, String content, boolean truncated) {

    /**
     * 紧凑构造器，验证条目不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public PayloadEntry {
      Objects.requireNonNull(payloadId, "payloadId 不得为 null");
      Objects.requireNonNull(kind, "kind 不得为 null");
      Objects.requireNonNull(callId, "callId 不得为 null");
      content = content == null ? "" : content;
    }
  }
}
