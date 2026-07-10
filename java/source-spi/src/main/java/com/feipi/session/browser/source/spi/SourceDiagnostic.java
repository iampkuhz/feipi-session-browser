package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.Optional;
import java.util.OptionalInt;

/**
 * 源解析诊断信息。
 *
 * <p>描述解析过程中遇到的单个问题。与 Python 端 {@code ParseIssueItem} 对齐。 不可变 record，所有字段通过构造时验证。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code severity} 不得为 null。
 *   <li>{@code issueType} 不得为 null。
 *   <li>{@code message} 不得为 null 或空。
 *   <li>{@code lineNo} 为正整数。
 *   <li>{@code code} 不得为 null 或空，表示稳定的诊断类型标识。
 * </ul>
 *
 * @param severity 诊断严重级别，不得为 null
 * @param issueType 问题类型标识，不得为 null
 * @param message 人类可读的问题描述，不得为空
 * @param lineNo 问题所在的源文件行号（从 1 开始）
 * @param preview 问题上下文预览文本，可选
 * @param code 稳定诊断代码，如 {@code "BAD_JSON"}、{@code "NON_OBJECT_SKIPPED"}，不得为空
 * @param locator 问题所在的源文件标识（相对路径或逻辑定位），不得为 null
 * @param column 问题所在的列号（从 1 开始），{@code empty} 表示未知
 * @param byteRangeStart 问题所在的字节范围起始（含），{@code empty} 表示未知
 * @param byteRangeEnd 问题所在的字节范围结束（不含），{@code empty} 表示未知
 */
@DomainModel
public record SourceDiagnostic(
    /* 诊断严重级别，不得为 null。 */
    @NotNull @CoreField ParseSeverity severity,

    /* 问题类型标识，不得为 null。 */
    @NotNull @CoreField ParseIssueType issueType,

    /* 人类可读的问题描述，不得为空。 */
    @NotNull @NotBlank @CoreField String message,

    /* 问题所在的源文件行号（从 1 开始）。 */
    @Positive @CoreField int lineNo,

    /* 问题上下文预览文本，可选。 */
    Optional<String> preview,

    /* 稳定诊断代码，不得为空。 */
    @NotNull @NotBlank @CoreField String code,

    /* 问题所在的源文件标识（相对路径或逻辑定位），不得为 null。 */
    @NotNull @CoreField String locator,

    /* 问题所在的列号（从 1 开始），empty 表示未知。 */
    OptionalInt column,

    /* 问题所在的字节范围起始（含），empty 表示未知。 */
    OptionalInt byteRangeStart,

    /* 问题所在的字节范围结束（不含），empty 表示未知。 */
    OptionalInt byteRangeEnd) {

  /**
   * 紧凑构造器，处理默认值并校验约束。
   *
   * @throws NullPointerException 当必填对象字段为 null 时
   * @throws IllegalArgumentException 当字符串为空或数值非法时
   */
  public SourceDiagnostic {
    preview = preview == null ? Optional.empty() : preview;
    column = column == null ? OptionalInt.empty() : column;
    byteRangeStart = byteRangeStart == null ? OptionalInt.empty() : byteRangeStart;
    byteRangeEnd = byteRangeEnd == null ? OptionalInt.empty() : byteRangeEnd;
    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceDiagnostic.class,
          severity,
          issueType,
          message,
          lineNo,
          preview,
          code,
          locator,
          column,
          byteRangeStart,
          byteRangeEnd);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  private static void translateValidation(ConstraintViolationException e) {
    var violations = e.getConstraintViolations();
    String[] notNullFields = {"severity", "issueType", "message", "code", "locator"};
    String[] blankFields = {"message", "code"};
    String[] positiveFields = {"lineNo"};
    for (String field : notNullFields) {
      for (var v : violations) {
        String path = v.getPropertyPath().toString();
        if ((path.equals(field) || path.endsWith("." + field))
            && v.getConstraintDescriptor().getAnnotation().annotationType() == NotNull.class) {
          throw new NullPointerException(field + " 不得为 null");
        }
      }
    }
    for (String field : blankFields) {
      for (var v : violations) {
        String path = v.getPropertyPath().toString();
        if ((path.equals(field) || path.endsWith("." + field))
            && v.getConstraintDescriptor().getAnnotation().annotationType() == NotBlank.class) {
          throw new IllegalArgumentException(field + " 不得为空");
        }
      }
    }
    for (String field : positiveFields) {
      for (var v : violations) {
        String path = v.getPropertyPath().toString();
        if ((path.equals(field) || path.endsWith("." + field))
            && v.getConstraintDescriptor().getAnnotation().annotationType()
                == jakarta.validation.constraints.Positive.class) {
          throw new IllegalArgumentException(field + " 必须为正整数");
        }
      }
    }
    throw e;
  }
}
