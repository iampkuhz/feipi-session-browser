package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.common.validation.ParamChecks;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.CallScope;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * 单次归一化逻辑 LLM 调用及其轻量级边引用。
 *
 * <p>语义构建器为主会话和子 agent 轮次创建这些记录，制品验证从 JSON 水合。 调用是不可变传输对象，其索引和键必须在制品内保持顺序。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code callId} 不得为 null 或空。
 *   <li>{@code callIndex} 必须 >= 1。
 *   <li>{@code callKey} 必须等于 {@code "C" + callIndex}。
 *   <li>{@code usage}、{@code request}、{@code response} 不得为 null。
 *   <li>所有集合字段使用不可变副本，大小不超过上限。
 * </ul>
 *
 * @param callId 稳定的适配器提供或生成的调用标识符
 * @param callIndex 归一化遍历顺序中从 1 开始的调用位置
 * @param callKey 显示键，格式为 {@code C{callIndex}}
 * @param scope 主会话或子 agent 作用域标签
 * @param parentCallId 子 agent 调用的父 LLM 调用，否则为空
 * @param parentToolCallId 触发子 agent 调用的工具调用边
 * @param turnId 关联的 provider 轮次标识符
 * @param model provider 报告的模型名称
 * @param timestamp provider 时间戳
 * @param usage 归因到该调用的 token 用量
 * @param request 请求侧边标识符
 * @param response 响应侧边标识符
 * @param sourceUnitRefRanges 对目录序列的引用列表
 * @param sourceUnits 内联源单元列表，兼容性保留
 * @param attributionCandidates 适配器归因元数据
 * @param usageSource 估算用量元数据
 * @param subagentId 子 agent 标识，主会话为空
 * @param parentToolName 触发子 agent 的父工具名，主会话为空
 */
@DomainModel
public record NormalizedCall(
    @CoreField String callId,
    @CoreField int callIndex,
    @CoreField String callKey,
    @CoreField CallScope scope,
    Optional<String> parentCallId,
    Optional<String> parentToolCallId,
    Optional<String> turnId,
    @CoreField String model,
    Optional<String> timestamp,
    @CoreField NormalizedCallUsage usage,
    @CoreField NormalizedCallRequest request,
    @CoreField NormalizedCallResponse response,
    List<SourceUnitRefRange> sourceUnitRefRanges,
    List<Map<String, Object>> sourceUnits,
    Map<String, Object> attributionCandidates,
    Map<String, Object> usageSource,
    Optional<String> subagentId,
    Optional<String> parentToolName) {

  /**
   * 兼容旧调用点的构造器。
   *
   * <p>旧调用点没有独立 subagent 标识和父工具名时，使用空值。
   */
  public NormalizedCall(
      String callId,
      int callIndex,
      String callKey,
      CallScope scope,
      Optional<String> parentCallId,
      Optional<String> parentToolCallId,
      Optional<String> turnId,
      String model,
      Optional<String> timestamp,
      NormalizedCallUsage usage,
      NormalizedCallRequest request,
      NormalizedCallResponse response,
      List<SourceUnitRefRange> sourceUnitRefRanges,
      List<Map<String, Object>> sourceUnits,
      Map<String, Object> attributionCandidates,
      Map<String, Object> usageSource) {
    this(
        callId,
        callIndex,
        callKey,
        scope,
        parentCallId,
        parentToolCallId,
        turnId,
        model,
        timestamp,
        usage,
        request,
        response,
        sourceUnitRefRanges,
        sourceUnits,
        attributionCandidates,
        usageSource,
        Optional.empty(),
        Optional.empty());
  }

  /**
   * 紧凑构造器，验证调用不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 callIndex 小于 1 或 callKey 不匹配时
   */
  public NormalizedCall {
    ParamChecks.nonEmpty(callId, "callId");
    ParamChecks.atLeast(callIndex, 1, "callIndex");
    Objects.requireNonNull(callKey, "callKey 不得为 null");
    String expectedKey = "C" + callIndex;
    if (!expectedKey.equals(callKey)) {
      throw new IllegalArgumentException(
          "callKey must match callIndex; expected '" + expectedKey + "', got '" + callKey + "'");
    }
    Objects.requireNonNull(scope, "scope 不得为 null");
    Objects.requireNonNull(model, "model 不得为 null");
    Objects.requireNonNull(usage, "usage 不得为 null");
    Objects.requireNonNull(request, "request 不得为 null");
    Objects.requireNonNull(response, "response 不得为 null");

    // Optional 字段规范化
    parentCallId = parentCallId == null ? Optional.empty() : parentCallId;
    parentToolCallId = parentToolCallId == null ? Optional.empty() : parentToolCallId;
    turnId = turnId == null ? Optional.empty() : turnId;
    timestamp = timestamp == null ? Optional.empty() : timestamp;
    subagentId = subagentId == null ? Optional.empty() : subagentId;
    parentToolName = parentToolName == null ? Optional.empty() : parentToolName;

    // 集合防御性拷贝
    sourceUnitRefRanges =
        ImmutableCopies.boundedListOrEmpty(
            sourceUnitRefRanges, NormalizedConstants.MAX_COLLECTION_SIZE, "sourceUnitRefRanges");
    sourceUnits =
        ImmutableCopies.boundedListOrEmpty(
            sourceUnits, NormalizedConstants.MAX_COLLECTION_SIZE, "sourceUnits");
    attributionCandidates =
        ImmutableCopies.boundedMapOrEmpty(
            attributionCandidates,
            NormalizedConstants.MAX_COLLECTION_SIZE,
            "attributionCandidates");
    usageSource =
        ImmutableCopies.boundedMapOrEmpty(
            usageSource, NormalizedConstants.MAX_COLLECTION_SIZE, "usageSource");
  }
}
