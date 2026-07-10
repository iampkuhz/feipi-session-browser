package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Objects;

/**
 * 源操作结果的密封类型。
 *
 * <p>将源适配器操作的最终状态封装为不可变的密封接口，禁止使用 null 或 boolean 表达模糊语义。每种状态对应一个 record 实现：
 *
 * <ul>
 *   <li>{@link Success} — 操作成功完成，携带源中性解析记录、诊断信息和定位器。
 *   <li>{@link RetryableIncomplete} — 操作未完成但可重试。
 *   <li>{@link Skipped} — 操作被有意跳过。
 *   <li>{@link Fatal} — 操作因不可恢复错误终止。
 * </ul>
 *
 * <p>使用 {@link #outcome()} 获取状态枚举值，或使用模式匹配处理各分支。
 */
@DomainModel
public sealed interface SourceResult
    permits SourceResult.Success,
        SourceResult.RetryableIncomplete,
        SourceResult.Skipped,
        SourceResult.Fatal {

  /** 最大诊断列表大小。 */
  int MAX_DIAGNOSTICS = 1000;

  /** 诊断列表为空时的统一错误消息。 */
  String DIAGNOSTICS_NULL_MESSAGE = "diagnostics 不得为 null";

  /** 诊断列表超限时的统一错误消息前缀。 */
  String DIAGNOSTICS_LIMIT_MESSAGE_PREFIX = "diagnostics size exceeds limit ";

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
   * <p>携带源中性解析记录、诊断信息、处理计数、指纹和定位器。
   *
   * @param diagnostics 诊断信息列表，不可变，不得为 null
   * @param candidateCount 成功处理的候选项数量，非负
   * @param records 源中性已解析记录列表，可能为空但永远不为 null
   * @param fingerprint 源文件指纹，{@code null} 表示不适用
   * @param locator 源定位标识，{@code null} 表示不适用
   */
  record Success(
      /* 诊断信息列表，不可变，不得为 null。 */
      List<SourceDiagnostic> diagnostics,

      /* 成功处理的候选项数量，非负。 */
      @PositiveOrZero @CoreField int candidateCount,

      /* 源中性已解析记录列表，可能为空但永远不为 null。 */
      List<SourceRecord> records,

      /* 源文件指纹，null 表示不适用。 */
      SourceFingerprint fingerprint,

      /* 源定位标识，null 表示不适用。 */
      String locator)
      implements SourceResult {

    /**
     * 紧凑构造器，执行防御性拷贝并校验约束。
     *
     * @throws IllegalArgumentException 当候选项数量为负或诊断超限时
     */
    public Success {
      Objects.requireNonNull(diagnostics, DIAGNOSTICS_NULL_MESSAGE);
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(DIAGNOSTICS_LIMIT_MESSAGE_PREFIX + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      records = records == null ? List.of() : List.copyOf(records);
      try {
        ValidationSupport.validateCanonicalConstructor(
            Success.class, diagnostics, candidateCount, records, fingerprint, locator);
      } catch (ConstraintViolationException e) {
        translatePositiveOrZero(e, "candidateCount");
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

    private static void translatePositiveOrZero(ConstraintViolationException e, String field) {
      for (var v : e.getConstraintViolations()) {
        String path = v.getPropertyPath().toString();
        if ((path.equals(field) || path.endsWith("." + field))
            && v.getConstraintDescriptor().getAnnotation().annotationType()
                == PositiveOrZero.class) {
          throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
        }
      }
      throw e;
    }
  }

  /**
   * 操作未完成但可在后续重试中恢复的结果。
   *
   * @param diagnostics 诊断信息列表，不可变，不得为 null
   * @param reason 可重试原因的简要描述，不得为空
   */
  record RetryableIncomplete(
      /* 诊断信息列表，不可变，不得为 null。 */
      List<SourceDiagnostic> diagnostics,

      /* 可重试原因的简要描述，不得为空。 */
      @NotNull @NotBlank @CoreField String reason)
      implements SourceResult {

    /**
     * 紧凑构造器，执行防御性拷贝并校验约束。
     *
     * @throws NullPointerException 当 reason 为 null 时
     * @throws IllegalArgumentException 当 reason 为空或诊断超限时
     */
    public RetryableIncomplete {
      Objects.requireNonNull(diagnostics, DIAGNOSTICS_NULL_MESSAGE);
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(DIAGNOSTICS_LIMIT_MESSAGE_PREFIX + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      try {
        ValidationSupport.validateCanonicalConstructor(
            RetryableIncomplete.class, diagnostics, reason);
      } catch (ConstraintViolationException e) {
        translateNotBlankNotNull(e, "reason");
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
   * @param diagnostics 诊断信息列表，不可变，不得为 null
   * @param reason 跳过原因的简要描述，不得为空
   */
  record Skipped(
      /* 诊断信息列表，不可变，不得为 null。 */
      List<SourceDiagnostic> diagnostics,

      /* 跳过原因的简要描述，不得为空。 */
      @NotNull @NotBlank @CoreField String reason)
      implements SourceResult {

    /**
     * 紧凑构造器，执行防御性拷贝并校验约束。
     *
     * @throws NullPointerException 当 reason 为 null 时
     * @throws IllegalArgumentException 当 reason 为空或诊断超限时
     */
    public Skipped {
      Objects.requireNonNull(diagnostics, DIAGNOSTICS_NULL_MESSAGE);
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(DIAGNOSTICS_LIMIT_MESSAGE_PREFIX + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      try {
        ValidationSupport.validateCanonicalConstructor(Skipped.class, diagnostics, reason);
      } catch (ConstraintViolationException e) {
        translateNotBlankNotNull(e, "reason");
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
   * @param diagnostics 诊断信息列表，不可变，不得为 null
   * @param errorDetail 错误详情，不得为空
   */
  record Fatal(
      /* 诊断信息列表，不可变，不得为 null。 */
      List<SourceDiagnostic> diagnostics,

      /* 错误详情，不得为空。 */
      @NotNull @NotBlank @CoreField String errorDetail)
      implements SourceResult {

    /**
     * 紧凑构造器，执行防御性拷贝并校验约束。
     *
     * @throws NullPointerException 当 errorDetail 为 null 时
     * @throws IllegalArgumentException 当 errorDetail 为空或诊断超限时
     */
    public Fatal {
      Objects.requireNonNull(diagnostics, DIAGNOSTICS_NULL_MESSAGE);
      List<SourceDiagnostic> copy = List.copyOf(diagnostics);
      if (copy.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(DIAGNOSTICS_LIMIT_MESSAGE_PREFIX + MAX_DIAGNOSTICS);
      }
      diagnostics = copy;
      try {
        ValidationSupport.validateCanonicalConstructor(Fatal.class, diagnostics, errorDetail);
      } catch (ConstraintViolationException e) {
        translateNotBlankNotNull(e, "errorDetail");
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

  /**
   * 将 NotBlank/NotNull 约束违反转换为对应的异常类型。
   *
   * <p>NotNull 违反抛出 NullPointerException；NotBlank 违反抛出 IllegalArgumentException（消息包含字段名）。
   */
  static void translateNotBlankNotNull(ConstraintViolationException e, String field) {
    for (var v : e.getConstraintViolations()) {
      String path = v.getPropertyPath().toString();
      if (!path.equals(field) && !path.endsWith("." + field)) {
        continue;
      }
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
    }
    for (var v : e.getConstraintViolations()) {
      String path = v.getPropertyPath().toString();
      if (!path.equals(field) && !path.endsWith("." + field)) {
        continue;
      }
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotBlank.class) {
        throw new IllegalArgumentException(field + " 不得为空");
      }
    }
    throw e;
  }
}
