package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.io.IOException;
import java.util.List;
import java.util.Objects;

/**
 * 源操作结果的密封类型。
 *
 * <p>将源适配器操作的最终状态封装为不可变的密封接口，禁止使用 null 或 boolean 表达模糊语义。每种状态对应一个不可变结果实现：
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
   * 操作成功完成的结果，同时拥有可重放记录序列的生命周期。
   *
   * <p>旧列表构造器保持五字段值语义。托管结果只保留序列句柄，不隐式读取或物化正文。 成功构造后所有权交给调用者；构造失败时仍由生产者清理输入序列。
   */
  final class Success implements SourceResult, AutoCloseable {
    private final List<SourceDiagnostic> diagnostics;
    @PositiveOrZero @CoreField private final int candidateCount;
    private final List<SourceRecord> records;
    private final SourceFingerprint fingerprint;
    private final String locator;
    private final SourceRecordSequence recordSequence;
    private boolean closed;

    /**
     * 构造兼容旧调用者的小列表结果，防御复制并保留原有校验。
     *
     * @param diagnostics 不可为 null 的诊断列表
     * @param candidateCount 非负候选项数量
     * @param records 记录列表，null 表示空列表
     * @param fingerprint 源指纹，可为 null
     * @param locator 源定位标识，可为 null
     */
    @java.beans.ConstructorProperties({
      "diagnostics",
      "candidateCount",
      "records",
      "fingerprint",
      "locator"
    })
    public Success(
        List<SourceDiagnostic> diagnostics,
        int candidateCount,
        List<SourceRecord> records,
        SourceFingerprint fingerprint,
        String locator) {
      this(diagnostics, candidateCount, records, fingerprint, locator, null);
    }

    /**
     * 保存已选择的列表或托管表示；不打开托管序列。
     *
     * @param diagnostics 不可为 null 的诊断列表
     * @param candidateCount 非负候选项数量
     * @param records 旧列表表示，托管表示时不使用
     * @param fingerprint 源指纹，可为 null
     * @param locator 源定位标识，可为 null
     * @param managedSequence 托管序列，null 表示使用旧列表
     */
    private Success(
        List<SourceDiagnostic> diagnostics,
        int candidateCount,
        List<SourceRecord> records,
        SourceFingerprint fingerprint,
        String locator,
        SourceRecordSequence managedSequence) {
      Objects.requireNonNull(diagnostics, DIAGNOSTICS_NULL_MESSAGE);
      this.diagnostics = List.copyOf(diagnostics);
      if (this.diagnostics.size() > MAX_DIAGNOSTICS) {
        throw new IllegalArgumentException(DIAGNOSTICS_LIMIT_MESSAGE_PREFIX + MAX_DIAGNOSTICS);
      }
      this.candidateCount = candidateCount;
      this.records =
          managedSequence == null ? (records == null ? List.of() : List.copyOf(records)) : null;
      this.fingerprint = fingerprint;
      this.locator = locator;
      this.recordSequence =
          managedSequence == null ? SourceRecordSequence.fromList(this.records) : managedSequence;
      try {
        ValidationSupport.validateBean(this);
      } catch (ConstraintViolationException e) {
        translatePositiveOrZero(e, "candidateCount");
      }
    }

    /**
     * 构造只保存句柄的托管结果，不遍历或复制序列记录。
     *
     * @param diagnostics 不可为 null 的诊断列表
     * @param candidateCount 非负候选项数量
     * @param sequence 成功构造后交由结果拥有的非 null 序列
     * @param fingerprint 源指纹，可为 null
     * @param locator 源定位标识，可为 null
     * @return 拥有输入序列的成功结果
     */
    public static Success managed(
        List<SourceDiagnostic> diagnostics,
        int candidateCount,
        SourceRecordSequence sequence,
        SourceFingerprint fingerprint,
        String locator) {
      return new Success(
          diagnostics,
          candidateCount,
          null,
          fingerprint,
          locator,
          Objects.requireNonNull(sequence, "sequence"));
    }

    /** 返回不可变诊断列表。 */
    @Override
    public List<SourceDiagnostic> diagnostics() {
      return diagnostics;
    }

    /** 返回非负候选项数量。 */
    public int candidateCount() {
      return candidateCount;
    }

    /**
     * 返回旧列表表示；托管结果必须通过独立游标读取。
     *
     * @return 不可变旧记录列表
     * @throws IllegalStateException 结果使用托管序列时
     */
    public List<SourceRecord> records() {
      if (hasManagedRecords()) {
        throw new IllegalStateException("managed records must be read through recordSequence()");
      }
      return records;
    }

    /** 返回源指纹，不适用时为 null。 */
    public SourceFingerprint fingerprint() {
      return fingerprint;
    }

    /** 返回源定位标识，不适用时为 null。 */
    public String locator() {
      return locator;
    }

    /** 返回结果拥有的同一序列句柄；借用者不得关闭所有者。 */
    public SourceRecordSequence recordSequence() {
      return recordSequence;
    }

    /** 返回是否采用托管表示，不以候选项或记录总数推测。 */
    public boolean hasManagedRecords() {
      return records == null;
    }

    /** 返回旧 JSON diagnostics 属性，不增加额外序列化状态。 */
    public List<SourceDiagnostic> getDiagnostics() {
      return diagnostics();
    }

    /** 返回旧 JSON candidateCount 属性。 */
    public int getCandidateCount() {
      return candidateCount();
    }

    /** 返回旧 JSON records 属性；托管结果明确拒绝隐式物化。 */
    public List<SourceRecord> getRecords() {
      return records();
    }

    /** 返回旧 JSON fingerprint 属性。 */
    public SourceFingerprint getFingerprint() {
      return fingerprint();
    }

    /** 返回旧 JSON locator 属性。 */
    public String getLocator() {
      return locator();
    }

    /** 返回成功状态。 */
    @Override
    public SourceOutcome outcome() {
      return SourceOutcome.SUCCESS;
    }

    /** 返回兼容原有调用者的成功消息。 */
    @Override
    public String message() {
      return "操作成功完成，处理 " + candidateCount + " 个候选项";
    }

    /**
     * 幂等关闭所属序列；清理失败传播给调用者，不吞掉异常。
     *
     * @throws IOException 所属序列资源释放失败时
     */
    @Override
    public void close() throws IOException {
      if (!closed) {
        closed = true;
        recordSequence.close();
      }
    }

    /**
     * 比较旧五字段值；托管结果额外要求拥有相同的序列句柄。
     *
     * @param other 待比较对象
     * @return 旧五字段相等且托管句柄一致时为真
     */
    @Override
    public boolean equals(Object other) {
      if (this == other) {
        return true;
      }
      if (!(other instanceof Success that)) {
        return false;
      }
      return candidateCount == that.candidateCount
          && diagnostics.equals(that.diagnostics)
          && Objects.equals(records, that.records)
          && Objects.equals(fingerprint, that.fingerprint)
          && Objects.equals(locator, that.locator)
          && (!hasManagedRecords() || recordSequence == that.recordSequence);
    }

    /** 保持旧 record 从零开始的五字段哈希算法；关闭状态不影响值语义。 */
    @Override
    public int hashCode() {
      int hash = diagnostics.hashCode();
      hash = 31 * hash + Integer.hashCode(candidateCount);
      hash = 31 * hash + Objects.hashCode(records);
      hash = 31 * hash + Objects.hashCode(fingerprint);
      hash = 31 * hash + Objects.hashCode(locator);
      return hasManagedRecords() ? 31 * hash + System.identityHashCode(recordSequence) : hash;
    }

    /** 保留旧 record 文本格式；托管状态不读取序列正文。 */
    @Override
    public String toString() {
      return "Success[diagnostics="
          + diagnostics
          + ", candidateCount="
          + candidateCount
          + ", records="
          + (hasManagedRecords() ? "<managed>" : records)
          + ", fingerprint="
          + fingerprint
          + ", locator="
          + locator
          + "]";
    }

    /**
     * 将负数约束违反翻译为旧调用者使用的异常。
     *
     * @param e 原始约束异常
     * @param field 候选数量字段名
     */
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
