package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.ScanFailure;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.ArrayList;
import java.util.List;

/** 将源诊断和扫描异常投影为不含原文的稳定失败原因。 */
public final class ScanDiagnostics {
  private ScanDiagnostics() {}

  /**
   * 汇总 ERROR 诊断；INFO/WARNING 不会把完整成功解析改为失败。
   *
   * @param diagnostics 源解析诊断
   * @return 安全的代码与行号串，没有 ERROR 时为空
   */
  public static String sourceErrors(List<SourceDiagnostic> diagnostics) {
    return diagnostics.stream()
        .filter(item -> item.severity() == ParseSeverity.ERROR)
        .map(item -> safeCode(item.code()) + "@" + item.lineNo())
        .collect(java.util.stream.Collectors.joining(";"));
  }

  /**
   * 构建可持久化和安全展示的失败信息，绝不复制 message/preview。
   *
   * @param issues 扫描问题
   * @return 安全失败原因
   */
  public static List<ScanFailure> failures(List<ScanIssue> issues) {
    List<ScanFailure> result = new ArrayList<>();
    for (ScanIssue issue : issues) {
      if (issue.message().startsWith("SOURCE_ERRORS:")) {
        for (String diagnostic : issue.message().substring("SOURCE_ERRORS:".length()).split(";")) {
          int separator = diagnostic.lastIndexOf('@');
          if (separator < 0 || !diagnostic.matches("[A-Z][A-Z0-9_]{0,79}@[0-9]{1,10}")) continue;
          try {
            result.add(
                new ScanFailure(
                    issue.sourceValue(),
                    issue.sessionKey(),
                    issue.phase().name(),
                    safeCode(diagnostic.substring(0, separator)),
                    Integer.parseInt(diagnostic.substring(separator + 1))));
          } catch (NumberFormatException ignored) {
            result.add(
                new ScanFailure(
                    issue.sourceValue(),
                    issue.sessionKey(),
                    issue.phase().name(),
                    "SOURCE_ERROR",
                    0));
          }
        }
      } else {
        String code = issue.phase().name() + "_FAILED";
        if (issue.phase() == ScanIssue.ScanPhase.NORMALIZE
            && issue.message().equals("TOOL_OWNER_UNAVAILABLE")) {
          code = "TOOL_OWNER_UNAVAILABLE";
        } else if (issue.message().contains("calls size exceeds limit")) {
          code = "NORMALIZED_CALL_LIMIT_EXCEEDED";
        }
        result.add(
            new ScanFailure(
                issue.sourceValue(), issue.sessionKey(), issue.phase().name(), code, 0));
      }
    }
    return List.copyOf(result);
  }

  private static String safeCode(String code) {
    String detail = code.startsWith("BAD_JSON:") ? code.substring("BAD_JSON:".length()) : code;
    return detail.matches("[A-Z][A-Z0-9_]{0,79}") ? detail : "SOURCE_ERROR";
  }
}
