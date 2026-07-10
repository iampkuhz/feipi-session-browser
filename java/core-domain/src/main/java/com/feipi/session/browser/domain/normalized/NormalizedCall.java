package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Map;
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
 * @param timestamp 适配层上报的时间戳文本
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
    /* 稳定的适配器提供或生成的调用标识符。 */
    @NotBlank @CoreField String callId,

    /* 归一化遍历顺序中从 1 开始的调用位置。 */
    @Positive @CoreField int callIndex,

    /* 显示键，格式为 {@code C{callIndex}}。 */
    @NotBlank @CoreField String callKey,

    /* 主会话或子 agent 作用域标签。 */
    @NotNull @CoreField CallScope scope,

    /* 子 agent 调用的父 LLM 调用，否则为空。 */
    Optional<String> parentCallId,

    /* 触发子 agent 调用的工具调用边。 */
    Optional<String> parentToolCallId,

    /* 关联的 provider 轮次标识符。 */
    Optional<String> turnId,

    /* provider 报告的模型名称。 */
    @NotNull @CoreField String model,

    /* 适配层上报的时间戳文本。 */
    Optional<String> timestamp,

    /* 归因到该调用的 token 用量。 */
    @NotNull @CoreField NormalizedCallUsage usage,

    /* 请求侧边标识符。 */
    @NotNull @CoreField NormalizedCallRequest request,

    /* 响应侧边标识符。 */
    @NotNull @CoreField NormalizedCallResponse response,

    /* 对目录序列的引用列表。 */
    @NotNull List<SourceUnitRefRange> sourceUnitRefRanges,

    /* 内联源单元列表，兼容性保留。 */
    @NotNull List<Map<String, Object>> sourceUnits,

    /* 适配器归因元数据。 */
    @NotNull Map<String, Object> attributionCandidates,

    /* 估算用量元数据。 */
    @NotNull Map<String, Object> usageSource,

    /* 子 agent 标识，主会话为空。 */
    Optional<String> subagentId,

    /* 触发子 agent 的父工具名，主会话为空。 */
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
   * @throws IllegalArgumentException 当 callKey 不匹配 callIndex 时
   */
  public NormalizedCall {
    // callKey 与 callIndex 跨字段规则
    String expectedKey = "C" + callIndex;
    if (!expectedKey.equals(callKey)) {
      throw new IllegalArgumentException(
          "callKey must match callIndex; expected '" + expectedKey + "', got '" + callKey + "'");
    }

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

    try {
      ValidationSupport.validateCanonicalConstructor(
          NormalizedCall.class,
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
          subagentId,
          parentToolName);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 将 Jakarta 校验违规翻译为向后兼容的异常类型。
   *
   * @param e 原始校验违规异常
   */
  private static void translateValidation(ConstraintViolationException e) {
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
    }
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotBlank.class) {
        if (v.getInvalidValue() == null) {
          throw new NullPointerException(field + " 不得为 null");
        }
        throw new IllegalArgumentException(field + " 不得为空");
      }
      if (type == Positive.class || type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 数值不合法: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
