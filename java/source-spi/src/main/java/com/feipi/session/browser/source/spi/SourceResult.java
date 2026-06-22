package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.List;
import java.util.Objects;

/**
 * 源操作结果的密封类型。
 *
 * <p>将源适配器操作的最终状态封装为不可变的密封接口，禁止使用 null 或 boolean
 * 表达模糊语义。每种状态对应一个 record 实现：
 *
 * <ul>
 *   <li>{@link Success} — 操作成功完成。
 *   <li>{@link RetryableIncomplete} — 操作未完成但可重试。
 *   <li>{@link Skipped} — 操作被有意跳过。
 *   <li>{@link Fatal} — 操作因不可恢复错误终止。
 * </ul>
 *
 * <p>使用 {@link #outcome()} 获取状态枚举值，或使用模式匹配处理各分支。
 */
@DomainModel
public sealed interface SourceResult permits
    SourceResult.Success,
    SourceResult.RetryableIncomplete,
    SourceResult.Skipped,
    SourceResult.Fatal {

  /** 最大诊断列表大小。 */
  int MAX_DIAGNOSTICS = 1000;

  /**
   * 返回操作结果的终端状态。
   *
   * @return 非 null 的 {@link SourceOutcome}
   */
  SourceOutcome outcome();

  /**
   * 返回操作过程中产生的诊断信息列表。
   *
   * @return 不可变诊断列表，可能为空但永远不为 null
   */
  List<SourceDiagnostic> diagnostics();

  /**
   * 返回操作结果的描述消息。
   *
   * @return 人类可读的结果描述
   */
  String message();

  /**
   * 操作成功完成的结果。
   *
   * @param diagnostics 诊断信息列表
   * @param candidateCount 成功处理的候选项数量
   */
  record Success(List<SourceDiagnostic> diagnostics, @CoreField int candidateCount)
      implements SourceResult {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws IllegalArgumentException 当候选项数量为负或诊断超限时
     */
    public Success {
      Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(
            "diagnostics size exceeds limit " + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      if (candidateCount < 0) {
        throw new IllegalArgumentException(
            "candidateCount 不得为负: " + candidateCount);
      }
    }

    @Override
    public SourceOutcome outcome() {
      return SourceOutcome.SUCCESS;
    }

    @Override
    public String message() {
      return "操作成功完成，处理 " + candidateCount + " 个候选项";
    }
  }

  /**
   * 操作未完成但可在后续重试中恢复的结果。
   *
   * @param diagnostics 诊断信息列表
   * @param reason 可重试原因的简要描述
   */
  record RetryableIncomplete(List<SourceDiagnostic> diagnostics, @CoreField String reason)
      implements SourceResult {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当 reason 为 null 时
     * @throws IllegalArgumentException 当 reason 为空或诊断超限时
     */
    public RetryableIncomplete {
      Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(
            "diagnostics size exceeds limit " + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      Objects.requireNonNull(reason, "reason 不得为 null");
      if (reason.isEmpty()) {
        throw new IllegalArgumentException("reason 不得为空");
      }
    }

    @Override
    public SourceOutcome outcome() {
      return SourceOutcome.RETRYABLE_INCOMPLETE;
    }

    @Override
    public String message() {
      return "操作未完成（可重试）: " + reason;
    }
  }

  /**
   * 操作被有意跳过的结果。
   *
   * @param diagnostics 诊断信息列表
   * @param reason 跳过原因的简要描述
   */
  record Skipped(List<SourceDiagnostic> diagnostics, @CoreField String reason)
      implements SourceResult {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当 reason 为 null 时
     * @throws IllegalArgumentException 当 reason 为空或诊断超限时
     */
    public Skipped {
      Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(
            "diagnostics size exceeds limit " + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      Objects.requireNonNull(reason, "reason 不得为 null");
      if (reason.isEmpty()) {
        throw new IllegalArgumentException("reason 不得为空");
      }
    }

    @Override
    public SourceOutcome outcome() {
      return SourceOutcome.SKIPPED;
    }

    @Override
    public String message() {
      return "操作已跳过: " + reason;
    }
  }

  /**
   * 操作因不可恢复错误终止的结果。
   *
   * @param diagnostics 诊断信息列表
   * @param errorDetail 错误详情
   */
  record Fatal(List<SourceDiagnostic> diagnostics, @CoreField String errorDetail)
      implements SourceResult {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当 errorDetail 为 null 时
     * @throws IllegalArgumentException 当 errorDetail 为空或诊断超限时
     */
    public Fatal {
      Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(
            "diagnostics size exceeds limit " + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      Objects.requireNonNull(errorDetail, "errorDetail 不得为 null");
      if (errorDetail.isEmpty()) {
        throw new IllegalArgumentException("errorDetail 不得为空");
      }
    }

    @Override
    public SourceOutcome outcome() {
      return SourceOutcome.FATAL;
    }

    @Override
    public String message() {
      return "操作致命错误: " + errorDetail;
    }
  }
}
