package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 单次归一化调用的 token 用量。
 *
 * <p>建模一次 LLM 调用的五字段 token 用量，语义构建器和制品验证器为每次调用创建这些不可变值对象。 分量计数必须非负，且 {@code total} 必须等于各分量之和。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有 token 计数必须非负。
 *   <li>{@code total} 必须等于 {@code fresh + cacheRead + cacheWrite + output}。
 * </ul>
 *
 * @param fresh 归因到该调用的非缓存输入 token 数
 * @param cacheRead 归因到该调用的缓存读取 token 数
 * @param cacheWrite 归因到该调用的缓存写入 token 数
 * @param output 归因到该调用的输出 token 数
 * @param total 所有 token 分量之和
 */
@DomainModel
public record NormalizedCallUsage(
    /* 归因到该调用的非缓存输入 token 数。 */
    @PositiveOrZero @CoreField long fresh,

    /* 归因到该调用的缓存读取 token 数。 */
    @PositiveOrZero @CoreField long cacheRead,

    /* 归因到该调用的缓存写入 token 数。 */
    @PositiveOrZero @CoreField long cacheWrite,

    /* 归因到该调用的输出 token 数。 */
    @PositiveOrZero @CoreField long output,

    /* 所有 token 分量之和。 */
    @PositiveOrZero @CoreField long total) {

  /**
   * 紧凑构造器，校验跨字段不变量。
   *
   * @throws IllegalArgumentException 当 {@code total} 不等于分量之和时
   */
  public NormalizedCallUsage {
    try {
      ValidationSupport.validateCanonicalConstructor(
          NormalizedCallUsage.class, fresh, cacheRead, cacheWrite, output, total);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
    // 跨字段规则：total 必须等于各分量之和
    long expectedTotal = fresh + cacheRead + cacheWrite + output;
    if (total != expectedTotal) {
      throw new IllegalArgumentException(
          "usage.total must equal component sum; expected=" + expectedTotal + ", got=" + total);
    }
  }

  /**
   * 创建全零的默认 token 用量。
   *
   * @return 所有 token 计数为零的默认实例
   */
  public static NormalizedCallUsage empty() {
    return new NormalizedCallUsage(0, 0, 0, 0, 0);
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
