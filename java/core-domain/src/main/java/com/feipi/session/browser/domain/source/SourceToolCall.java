package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * 源中性工具调用声明。
 *
 * <p>由 source adapter 在解析 provider 事件时提取，表示某条 assistant/source record 中声明的工具调用；不包含 provider 原始
 * payload。
 *
 * @param toolCallId 工具调用标识，来源于 provider 事件中的稳定 id
 * @param name 工具名称，来源于 provider 事件中的工具名字段
 * @param input 工具输入参数的 JSON 序列化文本（对象/数组/原文），缺失时为空字符串；不保存 JsonNode
 */
@DomainModel
public record SourceToolCall(
    /* 工具调用标识，来源于 provider 事件中的稳定 id。 */
    @NotBlank String toolCallId,

    /* 工具名称，来源于 provider 事件中的工具名字段。 */
    @NotBlank String name,

    /* 工具输入参数的 JSON 序列化文本，缺失时为空字符串。 */
    @NotNull String input) {

  /**
   * 兼容旧调用点的二参数构造器，input 默认为空字符串。
   *
   * @param toolCallId 工具调用标识
   * @param name 工具名称
   */
  public SourceToolCall(String toolCallId, String name) {
    this(toolCallId, name, "");
  }

  /** 紧凑构造器，校验约束并规范化 input 默认值。 */
  public SourceToolCall {
    input = input == null ? "" : input;
    try {
      ValidationSupport.validateCanonicalConstructor(SourceToolCall.class, toolCallId, name, input);
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
