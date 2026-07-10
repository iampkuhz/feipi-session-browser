package com.feipi.session.browser.domain;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.TokenPrecision;
import com.feipi.session.browser.domain.enums.TokenSourceKind;
import com.feipi.session.browser.domain.enums.TokenTotalSemantics;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 归一化后的 token 分类统计。
 *
 * <p>将一次 LLM 调用的 token 消耗按输入、缓存读取、缓存写入和输出四个维度分解， 同时记录计量的精度、合计语义和数据来源。 该类型被归一化引擎和制品写入层消费，用于 token
 * 分析面板和归因计算。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有 token 计数字段必须非负。
 *   <li>{@code rawFields} 和 {@code notes} 使用不可变副本，确保 record 不可变性。
 * </ul>
 *
 * @param freshInputTokens 非缓存的输入 token 数，非负
 * @param cacheReadTokens 缓存命中的读取 token 数，非负
 * @param cacheWriteTokens 缓存写入 token 数，非负
 * @param outputTokens 输出 token 数，非负
 * @param totalTokens 归一化后的 token 总计，非负
 * @param precision 计量精度级别
 * @param totalSemantics 合计字段的计算语义
 * @param sourceKind token 数据的来源分类
 * @param rawFields 原始未解析的附加字段，不可变
 * @param notes 附加说明信息列表，不可变
 */
@DomainModel
public record NormalizedTokenBreakdown(
    /* 非缓存的输入 token 数，非负。 */
    @PositiveOrZero @CoreField long freshInputTokens,

    /* 缓存命中的读取 token 数，非负。 */
    @PositiveOrZero @CoreField long cacheReadTokens,

    /* 缓存写入 token 数，非负。 */
    @PositiveOrZero @CoreField long cacheWriteTokens,

    /* 输出 token 数，非负。 */
    @PositiveOrZero @CoreField long outputTokens,

    /* 归一化后的 token 总计，非负。 */
    @PositiveOrZero @CoreField long totalTokens,

    /* 计量精度级别。 */
    @NotNull @CoreField TokenPrecision precision,

    /* 合计字段的计算语义。 */
    @NotNull @CoreField TokenTotalSemantics totalSemantics,

    /* token 数据的来源分类。 */
    @NotNull @CoreField TokenSourceKind sourceKind,

    /* 原始未解析的附加字段，不可变。 */
    Map<String, Object> rawFields,

    /* 附加说明信息列表，不可变。 */
    List<String> notes) {

  /**
   * 紧凑构造器，执行防御性拷贝并校验约束。
   *
   * <p>{@code rawFields} 和 {@code notes} 使用不可变副本替换， 确保 record 的不可变性语义。
   */
  public NormalizedTokenBreakdown {
    rawFields = ImmutableCopies.mapOrEmpty(rawFields);
    notes = ImmutableCopies.listOrEmpty(notes);
    try {
      ValidationSupport.validateCanonicalConstructor(
          NormalizedTokenBreakdown.class,
          freshInputTokens,
          cacheReadTokens,
          cacheWriteTokens,
          outputTokens,
          totalTokens,
          precision,
          totalSemantics,
          sourceKind,
          rawFields,
          notes);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 计算各分量 token 之和。
   *
   * @return 输入、缓存读取、缓存写入和输出 token 的合计值
   */
  public long componentTotal() {
    return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
  }

  /**
   * 创建全零的默认 token 分解实例。
   *
   * @return 所有 token 计数为零、精度为 {@code TokenPrecision#UNKNOWN} 的默认实例
   */
  public static NormalizedTokenBreakdown empty() {
    return new NormalizedTokenBreakdown(
        0,
        0,
        0,
        0,
        0,
        TokenPrecision.UNKNOWN,
        TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        TokenSourceKind.UNKNOWN,
        Collections.emptyMap(),
        Collections.emptyList());
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
      if (type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
