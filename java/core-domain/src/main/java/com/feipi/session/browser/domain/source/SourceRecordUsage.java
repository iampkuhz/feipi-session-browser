package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 源中性 token 用量。
 *
 * <p>用于承载 provider 解析阶段提取出的 token 分量；单位为 token，缺失或 unknown 时用 0 表示该分量未知/未提供，不表示 provider 真实用量一定为 0。
 *
 * @param inputTokens 新鲜输入 token 数，单位 token；未提供时为 0
 * @param cacheReadInputTokens 缓存读取输入 token 数，单位 token；未提供时为 0
 * @param cacheCreationInputTokens 缓存创建输入 token 数，单位 token；未提供时为 0
 * @param outputTokens 输出 token 数，单位 token；未提供时为 0
 */
@DomainModel
public record SourceRecordUsage(
    /* 新鲜输入 token 数，单位 token；未提供时为 0。 */
    @PositiveOrZero long inputTokens,

    /* 缓存读取输入 token 数，单位 token；未提供时为 0。 */
    @PositiveOrZero long cacheReadInputTokens,

    /* 缓存创建输入 token 数，单位 token；未提供时为 0。 */
    @PositiveOrZero long cacheCreationInputTokens,

    /* 输出 token 数，单位 token；未提供时为 0。 */
    @PositiveOrZero long outputTokens) {

  /** 紧凑构造器，校验约束。 */
  public SourceRecordUsage {
    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceRecordUsage.class,
          inputTokens,
          cacheReadInputTokens,
          cacheCreationInputTokens,
          outputTokens);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 返回空用量实例。
   *
   * @return 所有分量均为 0 的 token 用量
   */
  public static SourceRecordUsage empty() {
    return new SourceRecordUsage(0, 0, 0, 0);
  }

  /**
   * 返回总 token 数。
   *
   * @return 各 token 分量之和
   */
  public long total() {
    return inputTokens + cacheReadInputTokens + cacheCreationInputTokens + outputTokens;
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
