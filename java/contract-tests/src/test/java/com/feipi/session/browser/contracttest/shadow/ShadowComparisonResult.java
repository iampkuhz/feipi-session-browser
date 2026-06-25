package com.feipi.session.browser.contracttest.shadow;

import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Shadow 对比结果。
 *
 * <p>封装两条归一化制品的对比结论，包含总体分类和具体差异描述列表。
 *
 * @param category 差异总体分类
 * @param differences 具体差异描述列表，可能为空
 * @param baselineCalls 基线侧调用数量
 * @param candidateCalls 候选侧调用数量
 * @param baselineToolExecutions 基线侧工具执行数量
 * @param candidateToolExecutions 候选侧工具执行数量
 */
public record ShadowComparisonResult(
    ShadowDiffCategory category,
    List<String> differences,
    int baselineCalls,
    int candidateCalls,
    int baselineToolExecutions,
    int candidateToolExecutions) {

  public ShadowComparisonResult {
    Objects.requireNonNull(category, "category 不得为 null");
    differences = differences == null ? Collections.emptyList() : List.copyOf(differences);
  }

  /**
   * 判断对比结果是否允许切流。
   *
   * <p>{@code EXACT_MATCH} 和 {@code COMPATIBLE_DIFFERENCE} 视为可通过； {@code BREAKING_DIFFERENCE} 和
   * {@code INCOMPARABLE} 视为阻塞切流。
   *
   * @return 允许切流时返回 {@code true}
   */
  public boolean isCutoverSafe() {
    return category == ShadowDiffCategory.EXACT_MATCH
        || category == ShadowDiffCategory.COMPATIBLE_DIFFERENCE;
  }

  /**
   * 构建完全一致的结果。
   *
   * @param callCount 调用数量
   * @param toolCount 工具执行数量
   * @return 完全一致结果
   */
  public static ShadowComparisonResult exactMatch(int callCount, int toolCount) {
    return new ShadowComparisonResult(
        ShadowDiffCategory.EXACT_MATCH, List.of(), callCount, callCount, toolCount, toolCount);
  }

  /**
   * 构建无法对比的结果。
   *
   * @param reason 无法对比的原因
   * @return 无法对比结果
   */
  public static ShadowComparisonResult incomparable(String reason) {
    return new ShadowComparisonResult(ShadowDiffCategory.INCOMPARABLE, List.of(reason), 0, 0, 0, 0);
  }
}
