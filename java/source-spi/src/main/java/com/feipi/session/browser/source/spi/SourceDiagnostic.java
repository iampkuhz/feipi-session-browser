package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Objects;
import java.util.Optional;

/**
 * 源解析诊断信息。
 *
 * <p>描述解析过程中遇到的单个问题。与 Python 端 {@code ParseIssueItem} 对齐。
 * 不可变 record，所有字段通过构造时验证。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code severity} 不得为 null。
 *   <li>{@code issueType} 不得为 null。
 *   <li>{@code message} 不得为 null 或空。
 *   <li>{@code lineNo} 为正整数。
 * </ul>
 *
 * @param severity 诊断严重级别
 * @param issueType 问题类型标识
 * @param message 人类可读的问题描述
 * @param lineNo 问题所在的源文件行号（从 1 开始）
 * @param preview 问题上下文预览文本，可选
 */
@DomainModel
public record SourceDiagnostic(
    @CoreField ParseSeverity severity,
    @CoreField ParseIssueType issueType,
    @CoreField String message,
    @CoreField int lineNo,
    Optional<String> preview) {

  /**
   * 紧凑构造器，验证诊断不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当消息为空或行号非法时
   */
  public SourceDiagnostic {
    Objects.requireNonNull(severity, "severity 不得为 null");
    Objects.requireNonNull(issueType, "issueType 不得为 null");
    Objects.requireNonNull(message, "message 不得为 null");
    if (message.isEmpty()) {
      throw new IllegalArgumentException("message 不得为空");
    }
    if (lineNo < 1) {
      throw new IllegalArgumentException("lineNo 必须为正整数: " + lineNo);
    }
    preview = preview == null ? Optional.empty() : preview;
  }
}
