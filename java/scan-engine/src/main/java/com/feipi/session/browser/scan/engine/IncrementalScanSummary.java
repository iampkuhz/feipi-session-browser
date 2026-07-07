package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceId;
import java.util.List;
import java.util.Map;

/**
 * 增量扫描完成后的汇总结果。
 *
 * <p>在 {@link ScanSummary} 基础上增加增量扫描特有计数： unchanged（跳过）、changed（重新处理） 和 rebuild 触发标记。不可变、线程安全。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有计数非负。
 *   <li>{@code unchangedCount + changedCount + newCount + retryableCount == totalCandidates}。
 * </ul>
 *
 * @param totalCandidates 发现的候选项总数
 * @param successCount 成功处理的候选项数（new + changed 中成功的）
 * @param skippedCount 因非指纹原因跳过的候选项数（如 age cutoff、agent 过滤）
 * @param errorCount 处理失败的候选项数
 * @param scanDurationMs 扫描总耗时（毫秒）
 * @param scanLogId scan_log 表记录 ID
 * @param perSourceCount 各源处理的候选项数
 * @param issues 扫描过程中遇到的问题列表
 * @param unchangedCount 指纹匹配未处理的候选项数
 * @param changedCount 指纹变化重新处理的候选项数
 * @param newCount 新发现的候选项数
 * @param retryableCount 重试的候选项数
 * @param rebuildTriggered scan logic version 变化是否触发了全量重建
 */
public record IncrementalScanSummary(
    int totalCandidates,
    int successCount,
    int skippedCount,
    int errorCount,
    long scanDurationMs,
    long scanLogId,
    Map<SourceId, Integer> perSourceCount,
    List<ScanIssue> issues,
    int unchangedCount,
    int changedCount,
    int newCount,
    int retryableCount,
    boolean rebuildTriggered) {

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws IllegalArgumentException 当计数为负时
   */
  public IncrementalScanSummary {
    ScanSummarySupport.requireNonNegative("totalCandidates", totalCandidates);
    ScanSummarySupport.requireNonNegative("successCount", successCount);
    ScanSummarySupport.requireNonNegative("skippedCount", skippedCount);
    ScanSummarySupport.requireNonNegative("errorCount", errorCount);
    ScanSummarySupport.requireNonNegative("scanDurationMs", scanDurationMs);
    ScanSummarySupport.requireNonNegative("unchangedCount", unchangedCount);
    ScanSummarySupport.requireNonNegative("changedCount", changedCount);
    ScanSummarySupport.requireNonNegative("newCount", newCount);
    ScanSummarySupport.requireNonNegative("retryableCount", retryableCount);
    perSourceCount = ScanSummarySupport.copyPerSourceCount(perSourceCount);
    issues = ScanSummarySupport.copyIssues(issues);
  }

  /**
   * 从基础 {@link ScanSummary} 和增量计数构建。
   *
   * @param base 基础扫描汇总
   * @param unchangedCount 未变化计数
   * @param changedCount 变化计数
   * @param newCount 新增计数
   * @param retryableCount 重试计数
   * @param rebuildTriggered 是否触发重建
   * @return 增量扫描汇总
   */
  public static IncrementalScanSummary fromBase(
      ScanSummary base,
      int unchangedCount,
      int changedCount,
      int newCount,
      int retryableCount,
      boolean rebuildTriggered) {
    return new IncrementalScanSummary(
        base.totalCandidates(),
        base.successCount(),
        base.skippedCount(),
        base.errorCount(),
        base.scanDurationMs(),
        base.scanLogId(),
        base.perSourceCount(),
        base.issues(),
        unchangedCount,
        changedCount,
        newCount,
        retryableCount,
        rebuildTriggered);
  }
}
