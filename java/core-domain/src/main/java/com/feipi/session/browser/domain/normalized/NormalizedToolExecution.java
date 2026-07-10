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
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Optional;

/**
 * 工具执行边表行。
 *
 * <p>建模由一次调用声明并被另一次调用消费的工具调用边。语义构建器在遍历工具批次时生成这些记录， 制品验证器将它们水合为不可变边元数据。当 provider 未报告执行详情时，可选字段为空。
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
 * @param resultConsumedByCallId 消费该工具结果的后续调用标识符
 * @param status 可选的非完成状态详情
 * @param exitCode 可选的进程风格退出码
 * @param durationMs 非负的执行时长（毫秒）
 * @param filesTouched 工具执行涉及的文件列表
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

    /* 消费该工具结果的后续调用标识符。 */
    Optional<String> resultConsumedByCallId,

    /* 可选的非完成状态详情。 */
    Optional<String> status,

    /* 可选的进程风格退出码。 */
    Optional<Integer> exitCode,

    /* 非负的执行时长（毫秒）。 */
    @PositiveOrZero long durationMs,

    /* 工具执行涉及的文件列表。 */
    List<String> filesTouched,

    /* 可选的关联子 agent 实例标识。 */
    Optional<String> subagentId) {

  /**
   * 紧凑构造器，处理默认值并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public NormalizedToolExecution {
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
          subagentId);
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
