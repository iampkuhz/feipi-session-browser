package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;

/**
 * 源中性工具调用声明。
 *
 * <p>由 source adapter 在解析 provider 事件时提取，表示某条 assistant/source record 中声明的工具调用；不包含 provider 原始
 * payload。
 *
 * @param toolCallId 工具调用标识，来源于 provider 事件中的稳定 id
 * @param name 工具名称，来源于 provider 事件中的工具名字段
 */
@DomainModel
public record SourceToolCall(
    /* 工具调用标识，来源于 provider 事件中的稳定 id。 */
    @NotBlank String toolCallId,

    /* 工具名称，来源于 provider 事件中的工具名字段。 */
    @NotBlank String name) {

  /** 紧凑构造器，校验约束。 */
  public SourceToolCall {
    try {
      ValidationSupport.validateCanonicalConstructor(SourceToolCall.class, toolCallId, name);
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
      if (type == NotBlank.class) {
        throw new IllegalArgumentException(field + " 不得为空");
      }
    }
    throw e;
  }
}
