package com.feipi.session.browser.scan.engine;

/**
 * 扫描进度回调接口。
 *
 * <p>在扫描引擎处理候选项过程中，通过该接口向调用方报告进度。 调用方可实现此接口以在控制台显示进度条或执行其他进度跟踪操作。
 *
 * <p>所有方法的参数均保证非 null（sourceName 为 source id 的 value，如 {@code "claude_code"}）。
 */
public interface ScanProgress {

  /**
   * 某个源开始处理前调用。
   *
   * @param sourceName 源标识，如 {@code "claude_code"}、{@code "codex"}、{@code "qoder"}
   * @param candidateCount 该源发现的候选项总数
   */
  void onSourceStart(String sourceName, int candidateCount);

  /**
   * 每处理一个候选项后调用。
   *
   * @param sourceName 源标识
   * @param processed 已处理的候选项数量
   * @param total 该源的候选项总数
   */
  void onCandidateProcessed(String sourceName, int processed, int total);

  /**
   * 某个源的所有候选项处理完毕后调用。
   *
   * @param sourceName 源标识
   * @param successCount 该源成功处理的候选项数量
   */
  void onSourceEnd(String sourceName, int successCount);
}
