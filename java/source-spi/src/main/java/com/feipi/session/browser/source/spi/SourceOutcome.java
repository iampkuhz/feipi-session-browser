package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 源操作结果状态。
 *
 * <p>严格区分四种终端状态，禁止使用 null 或 boolean 表达模糊语义。
 * 每个枚举常量明确表示源适配器操作后的最终结论：
 *
 * <ul>
 *   <li>{@link #SUCCESS} — 操作完成，结果可用。
 *   <li>{@link #RETRYABLE_INCOMPLETE} — 操作未完成但可在后续重试中恢复。
 *   <li>{@link #SKIPPED} — 操作因前置条件不满足而被有意跳过。
 *   <li>{@link #FATAL} — 操作因不可恢复错误终止。
 * </ul>
 */
@DomainModel
public enum SourceOutcome {

  /** 操作成功完成，结果数据完整可用。 */
  @CoreField SUCCESS,

  /** 操作未完成但可在后续重试中恢复，例如文件正在被写入。 */
  @CoreField RETRYABLE_INCOMPLETE,

  /** 操作因前置条件不满足而被有意跳过，例如目录不存在。 */
  @CoreField SKIPPED,

  /** 操作因不可恢复错误终止，例如权限拒绝或数据损坏。 */
  @CoreField FATAL;

  /**
   * 判断该状态是否表示操作成功。
   *
   * @return 当且仅当状态为 {@link #SUCCESS} 时返回 {@code true}
   */
  public boolean isSuccess() {
    return this == SUCCESS;
  }

  /**
   * 判断该状态是否表示可重试的不完整状态。
   *
   * @return 当且仅当状态为 {@link #RETRYABLE_INCOMPLETE} 时返回 {@code true}
   */
  public boolean isRetryable() {
    return this == RETRYABLE_INCOMPLETE;
  }

  /**
   * 判断该状态是否表示终端失败（不可恢复）。
   *
   * @return 当且仅当状态为 {@link #FATAL} 时返回 {@code true}
   */
  public boolean isFatal() {
    return this == FATAL;
  }
}
