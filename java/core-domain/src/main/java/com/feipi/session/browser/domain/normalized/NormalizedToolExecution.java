package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * 工具执行边表行。
 *
 * <p>建模工具调用的声明归属及可统一表示的结果消费关系。语义构建器在遍历工具批次时生成这些记录， 制品验证器将它们水合为不可变边元数据。当 provider 未报告执行详情时，可选字段为空。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code toolCallId}、{@code name}、{@code declaredByCallId} 不得为 null。
 *   <li>{@code toolCallId} 不得为空字符串。
 *   <li>{@code durationMs} 必须非负。
 *   <li>{@code filesTouched} 使用不可变副本。
 * </ul>
 *
 * @param toolCallId 稳定的工具调用标识符
 * @param name provider 报告的工具名称
 * @param scope 工具执行的作用域（main/subagent）
 * @param declaredByCallId 声明该工具调用的调用标识符
 * @param resultConsumedByCallId 全部已观察结果均由同一后续调用消费时的标识符；为空不代表无结果或从未消费，逐次关联以各调用的请求为准
 * @param status 可选的非完成状态详情
 * @param exitCode 可选的进程风格退出码
 * @param durationMs 非负的执行时长（毫秒），未知时为空
 * @param filesTouched 工具执行涉及的文件列表
 * @param collaboration 与工具 occurrence 绑定的紧凑协作事实
 * @param observation 显式执行器观测，与启发式 status 分开
 * @param subagentId 可选的关联子 agent 实例标识
 */
@DomainModel
public record NormalizedToolExecution(
    /* 稳定的工具调用标识符。 */
    @NotBlank @CoreField String toolCallId,

    /* provider 报告的工具名称。 */
    @NotBlank @CoreField String name,

    /* 工具执行的作用域（main/subagent）。 */
    @NotNull @CoreField CallScope scope,

    /* 声明该工具调用的调用标识符。 */
    @NotBlank @CoreField String declaredByCallId,

    /* 全部已观察结果的一致消费调用摘要；为空不清除各请求已知的结果关联。 */
    Optional<String> resultConsumedByCallId,

    /* 可选的非完成状态详情。 */
    Optional<String> status,

    /* 可选的进程风格退出码。 */
    Optional<Integer> exitCode,

    /* 非负的执行时长（毫秒）。 */
    @PositiveOrZero Long durationMs,

    /* 工具执行涉及的文件列表。 */
    List<String> filesTouched,

    /* 可选的关联子 agent 实例标识。 */
    Optional<String> subagentId,
    Optional<SourceToolObservation> observation,
    List<NormalizedCollaborationAction> collaboration) {

  /** 未携带协作事实的源码便利入口。 */
  public NormalizedToolExecution(
      String toolCallId,
      String name,
      CallScope scope,
      String declaredByCallId,
      Optional<String> resultConsumedByCallId,
      Optional<String> status,
      Optional<Integer> exitCode,
      Long durationMs,
      List<String> filesTouched,
      Optional<String> subagentId,
      Optional<SourceToolObservation> observation) {
    this(
        toolCallId,
        name,
        scope,
        declaredByCallId,
        resultConsumedByCallId,
        status,
        exitCode,
        durationMs,
        filesTouched,
        subagentId,
        observation,
        List.of());
  }

  /** 保留工具摘要，只替换有界协作事实。 */
  public NormalizedToolExecution withCollaboration(List<NormalizedCollaborationAction> facts) {
    return new NormalizedToolExecution(
        toolCallId,
        name,
        scope,
        declaredByCallId,
        resultConsumedByCallId,
        status,
        exitCode,
        durationMs,
        filesTouched,
        subagentId,
        observation,
        facts);
  }

  /** 未携带执行器观测的源码调用入口。 */
  public NormalizedToolExecution(
      String toolCallId,
      String name,
      CallScope scope,
      String declaredByCallId,
      Optional<String> resultConsumedByCallId,
      Optional<String> status,
      Optional<Integer> exitCode,
      long durationMs,
      List<String> filesTouched,
      Optional<String> subagentId) {
    this(
        toolCallId,
        name,
        scope,
        declaredByCallId,
        resultConsumedByCallId,
        status,
        exitCode,
        durationMs,
        filesTouched,
        subagentId,
        Optional.empty());
  }

  /**
   * 紧凑构造器，处理默认值并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public NormalizedToolExecution {
    collaboration = List.copyOf(collaboration == null ? List.of() : collaboration);
    if (collaboration.size() > 256) throw new IllegalArgumentException("工具协作事实超限");
    observation = observation == null ? Optional.empty() : observation;
    if (observation.isPresent()) {
      var value = observation.orElseThrow();
      if (!value.toolCallId().equals(toolCallId)
          || !Objects.equals(value.measuresTool() ? value.durationMs() : null, durationMs)
          || !Objects.equals(
              value.measuresTool() ? value.exitCode() : null,
              exitCode == null ? null : exitCode.orElse(null))) {
        throw new IllegalArgumentException("工具观测与执行摘要不一致");
      }
    }
    // Optional 字段规范化
    resultConsumedByCallId =
        resultConsumedByCallId == null ? Optional.empty() : resultConsumedByCallId;
    status = status == null ? Optional.empty() : status;
    exitCode = exitCode == null ? Optional.empty() : exitCode;
    subagentId = subagentId == null ? Optional.empty() : subagentId;

    // 集合防御性拷贝
    filesTouched =
        ImmutableCopies.boundedListOrEmpty(
            filesTouched, NormalizedConstants.MAX_COLLECTION_SIZE, "filesTouched");

    try {
      ValidationSupport.validateCanonicalConstructor(
          NormalizedToolExecution.class,
          toolCallId,
          name,
          scope,
          declaredByCallId,
          resultConsumedByCallId,
          status,
          exitCode,
          durationMs,
          filesTouched,
          subagentId,
          observation,
          collaboration);
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
      if (type == NotBlank.class) {
        throw new IllegalArgumentException(field + " 不得为空");
      }
      if (type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
