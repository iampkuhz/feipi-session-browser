package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Map;

/**
 * Full scan 完成后的汇总结果。
 *
 * <p>记录本次扫描的候选项计数、各源分布、错误列表和扫描时长。 不可变、线程安全。
 *
 * @param totalCandidates 发现的候选项总数
 * @param successCount 成功处理的候选项数
 * @param skippedCount 被跳过的候选项数
 * @param errorCount 处理失败的候选项数
 * @param scanDurationMs 扫描总耗时（毫秒）
 * @param scanLogId scan_log 表记录 ID，0 表示未写入 scan_log
 * @param perSourceCount 各源处理的候选项数
 * @param issues 扫描过程中遇到的问题列表
 */
public record ScanSummary(
    /* 发现的候选项总数。 */
    @PositiveOrZero int totalCandidates,

    /* 成功处理的候选项数。 */
    @PositiveOrZero int successCount,

    /* 被跳过的候选项数。 */
    @PositiveOrZero int skippedCount,

    /* 处理失败的候选项数。 */
    @PositiveOrZero int errorCount,

    /* 扫描总耗时（毫秒）。 */
    @PositiveOrZero long scanDurationMs,

    /* scan_log 表记录 ID，0 表示未写入 scan_log。 */
    @PositiveOrZero long scanLogId,

    /* 各源处理的候选项数。 */
    @NotNull Map<SourceId, Integer> perSourceCount,

    /* 扫描过程中遇到的问题列表。 */
    @NotNull List<ScanIssue> issues) {

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws IllegalArgumentException 当计数为负时
   */
  public ScanSummary {
    ValidationSupport.validateCanonicalConstructor(
        ScanSummary.class,
        totalCandidates,
        successCount,
        skippedCount,
        errorCount,
        scanDurationMs,
        scanLogId,
        perSourceCount,
        issues);
    perSourceCount = ScanSummarySupport.copyPerSourceCount(perSourceCount);
    issues = ScanSummarySupport.copyIssues(issues);
  }

  /**
   * 判断扫描是否完全成功（无错误）。
   *
   * @return 无错误时返回 {@code true}
   */
  public boolean isFullySuccessful() {
    return errorCount == 0;
  }
}
