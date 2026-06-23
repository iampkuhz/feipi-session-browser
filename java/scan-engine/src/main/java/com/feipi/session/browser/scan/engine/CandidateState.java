package com.feipi.session.browser.scan.engine;

/**
 * 增量扫描候选项状态。
 *
 * <p>状态机描述每个发现的候选项在指纹比较后的处理路径。 状态由 {@link IncrementalScanEngine} 在发现阶段后逐一分类。
 *
 * <p>状态转移规则：
 *
 * <ul>
 *   <li>{@link #NEW} — sessions 表中无对应 session_key，需完整处理管线。
 *   <li>{@link #UNCHANGED} — 指纹匹配，跳过解析和写入。
 *   <li>{@link #CHANGED} — 指纹不匹配，需重新解析并更新 artifact 和 index。
 *   <li>{@link #RETRYABLE} — 上次解析未完成（如写入中断），保留旧有效状态并重新尝试。
 * </ul>
 */
public enum CandidateState {
  /** 新候选项，索引中不存在。 */
  NEW,
  /** 指纹匹配，无需重新处理。 */
  UNCHANGED,
  /** 指纹不匹配，需重新处理。 */
  CHANGED,
  /** 上次处理未完成，可重试。 */
  RETRYABLE
}
