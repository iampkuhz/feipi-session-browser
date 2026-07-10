package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 源内容字节偏移范围。
 *
 * <p>表示源单元在原始文件中的字节偏移区间，用于精确定位归因内容。 {@code start} 为包含起始偏移，{@code end} 为排除结束偏移。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code start} 和 {@code end} 必须非负。
 *   <li>{@code end} 必须大于等于 {@code start}。
 * </ul>
 *
 * @param start 包含起始字节偏移
 * @param end 排除结束字节偏移
 */
@DomainModel
public record ByteRange(
    /* 包含起始字节偏移。 */
    @PositiveOrZero @CoreField long start,

    /* 排除结束字节偏移。 */
    @PositiveOrZero @CoreField long end) {

  /**
   * 紧凑构造器，验证字节范围不变量。
   *
   * @throws IllegalArgumentException 当 {@code end} 小于 {@code start} 时
   */
  public ByteRange {
    if (end < start) {
      throw new IllegalArgumentException(
          "byte_range.end must be >= start; start=" + start + ", end=" + end);
    }
    try {
      ValidationSupport.validateCanonicalConstructor(ByteRange.class, start, end);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 创建零长度的空字节范围。
   *
   * @return {@code start} 和 {@code end} 均为 0 的空范围
   */
  public static ByteRange empty() {
    return new ByteRange(0, 0);
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
      if (type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
