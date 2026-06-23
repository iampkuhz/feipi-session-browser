package com.feipi.session.browser.query.api;

import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * 单个索引会话的域级解析诊断。
 *
 * <p>Source adapter 从 JSONL reader 诊断构建此对象，可在索引写入前追加 adapter 特定问题。
 * 计数属性从不可变问题列表派生。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 不得为 null，空字符串表示会话键缺失。
 *   <li>{@code filePath} 不得为 null，空字符串表示文件路径缺失。
 *   <li>{@code totalLines} 非负。
 *   <li>{@code eventsParsed} 非负。
 *   <li>{@code eventsSkipped} 非负。
 *   <li>{@code issues} 不得为 null，使用不可变列表。
 * </ul>
 *
 * @param sessionKey 会话主键
 * @param filePath 源文件路径
 * @param totalLines reader 读取的总行数
 * @param eventsParsed reader 接受的事件对象数
 * @param eventsSkipped 解析时跳过的条目数
 * @param issues 解析问题列表
 */
public record SessionParseDiagnostics(
    String sessionKey,
    String filePath,
    long totalLines,
    long eventsParsed,
    long eventsSkipped,
    List<DiagnosticIssueItem> issues) {

  /**
   * 紧凑构造器，验证解析诊断不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当计数字段为负数时
   */
  public SessionParseDiagnostics {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(filePath, "filePath 不得为 null");
    if (totalLines < 0) {
      throw new IllegalArgumentException("totalLines 必须非负; got " + totalLines);
    }
    if (eventsParsed < 0) {
      throw new IllegalArgumentException("eventsParsed 必须非负; got " + eventsParsed);
    }
    if (eventsSkipped < 0) {
      throw new IllegalArgumentException("eventsSkipped 必须非负; got " + eventsSkipped);
    }
    Objects.requireNonNull(issues, "issues 不得为 null");
    issues = List.copyOf(issues);
  }

  /**
   * 创建无问题的空诊断。
   *
   * @param sessionKey 会话主键
   * @param filePath 源文件路径
   * @return 空问题列表的诊断实例
   */
  public static SessionParseDiagnostics empty(String sessionKey, String filePath) {
    return new SessionParseDiagnostics(sessionKey, filePath, 0, 0, 0, Collections.emptyList());
  }

  /**
   * 是否存在严重解析问题。
   *
   * @return 至少有一个 CRITICAL 严重度问题时返回 true
   */
  public boolean hasCritical() {
    return issues.stream().anyMatch(i -> i.severity() == DiagnosticSeverity.CRITICAL);
  }

  /**
   * 是否存在警告级解析问题。
   *
   * @return 至少有一个 WARNING 严重度问题时返回 true
   */
  public boolean hasWarnings() {
    return issues.stream().anyMatch(i -> i.severity() == DiagnosticSeverity.WARNING);
  }

  /**
   * 严重问题数量。
   *
   * @return CRITICAL 严重度的问题数量
   */
  public long criticalCount() {
    return issues.stream().filter(i -> i.severity() == DiagnosticSeverity.CRITICAL).count();
  }

  /**
   * 警告级问题数量。
   *
   * @return WARNING 严重度的问题数量
   */
  public long warningCount() {
    return issues.stream().filter(i -> i.severity() == DiagnosticSeverity.WARNING).count();
  }

  /**
   * 信息级问题数量。
   *
   * @return INFO 严重度的问题数量
   */
  public long infoCount() {
    return issues.stream().filter(i -> i.severity() == DiagnosticSeverity.INFO).count();
  }
}
