package com.feipi.session.browser.domain;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.enums.TokenPrecision;
import com.feipi.session.browser.domain.enums.TokenSourceKind;
import com.feipi.session.browser.domain.enums.TokenTotalSemantics;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 归一化后的 token 分类统计。
 *
 * <p>将一次 LLM 调用的 token 消耗按输入、缓存读取、缓存写入和输出四个维度分解， 同时记录计量的精度、合计语义和数据来源。 该类型被 {@code SessionSummary} 和
 * 网页展示层消费，用于 token 分析面板和归因计算。
 *
 * @param freshInputTokens 非缓存的输入 token 数
 * @param cacheReadTokens 缓存命中的读取 token 数
 * @param cacheWriteTokens 缓存写入 token 数
 * @param outputTokens 输出 token 数
 * @param totalTokens 归一化后的 token 总计
 * @param precision 计量精度级别
 * @param totalSemantics 合计字段的计算语义
 * @param sourceKind token 数据的来源分类
 * @param rawFields 原始未解析的附加字段，不可变
 * @param notes 附加说明信息列表，不可变
 */
@DomainModel
public record NormalizedTokenBreakdown(
    @CoreField long freshInputTokens,
    @CoreField long cacheReadTokens,
    @CoreField long cacheWriteTokens,
    @CoreField long outputTokens,
    @CoreField long totalTokens,
    @CoreField TokenPrecision precision,
    @CoreField TokenTotalSemantics totalSemantics,
    @CoreField TokenSourceKind sourceKind,
    Map<String, Object> rawFields,
    List<String> notes) {

  /**
   * 紧凑构造器，执行防御性拷贝和非空约束。
   *
   * <p>{@code rawFields} 和 {@code notes} 使用不可变副本替换， 确保 record 的不可变性语义。
   */
  public NormalizedTokenBreakdown {
    Objects.requireNonNull(precision, "precision 不得为 null");
    Objects.requireNonNull(totalSemantics, "totalSemantics 不得为 null");
    Objects.requireNonNull(sourceKind, "sourceKind 不得为 null");
    rawFields = rawFields == null ? Map.of() : Map.copyOf(rawFields);
    notes = notes == null ? List.of() : List.copyOf(notes);
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
}
