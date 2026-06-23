package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 单个解析级别问题。
 *
 * <p>JSONL 诊断桥接器在转换原始 reader 诊断时创建此对象。行号 {@code 0} 表示文件级问题； 正值标识 JSONL 行号。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code issue} 不得为 null。
 *   <li>{@code severity} 不得为 null。
 *   <li>{@code message} 不得为 null，空字符串表示消息缺失。
 *   <li>{@code lineNo} 非负，{@code 0} 表示文件级问题。
 *   <li>{@code detail} 不得为 null，空字符串表示无附加详情。
 * </ul>
 *
 * @param issue 问题类别
 * @param severity 问题严重度
 * @param message 人类可读的问题消息
 * @param lineNo 源文件行号，{@code 0} 表示文件级问题
 * @param detail 附加上下文信息（如错误 JSON 预览）
 */
public record DiagnosticIssueItem(
    DiagnosticIssue issue, DiagnosticSeverity severity, String message, int lineNo, String detail) {

  /**
   * 紧凑构造器，验证解析问题项不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当行号为负数时
   */
  public DiagnosticIssueItem {
    Objects.requireNonNull(issue, "issue 不得为 null");
    Objects.requireNonNull(severity, "severity 不得为 null");
    Objects.requireNonNull(message, "message 不得为 null");
    if (lineNo < 0) {
      throw new IllegalArgumentException("lineNo 必须非负; got " + lineNo);
    }
    detail = detail == null ? "" : detail;
  }

  /**
   * 创建文件级问题（行号为 0）。
   *
   * @param issue 问题类别
   * @param severity 问题严重度
   * @param message 问题消息
   * @return 新的文件级问题实例
   */
  public static DiagnosticIssueItem fileLevel(
      DiagnosticIssue issue, DiagnosticSeverity severity, String message) {
    return new DiagnosticIssueItem(issue, severity, message, 0, "");
  }

  /**
   * 创建带详情的行级问题。
   *
   * @param issue 问题类别
   * @param severity 问题严重度
   * @param message 问题消息
   * @param lineNo JSONL 行号
   * @param detail 附加详情
   * @return 新的行级问题实例
   */
  public static DiagnosticIssueItem withDetail(
      DiagnosticIssue issue,
      DiagnosticSeverity severity,
      String message,
      int lineNo,
      String detail) {
    return new DiagnosticIssueItem(issue, severity, message, lineNo, detail);
  }
}
