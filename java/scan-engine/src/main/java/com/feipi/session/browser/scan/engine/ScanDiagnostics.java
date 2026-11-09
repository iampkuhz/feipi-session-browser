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
      if (!issue.code().isEmpty()) {
        result.add(
            new ScanFailure(
                issue.sourceValue(),
                issue.sessionKey(),
                issue.phase().name(),
                safeCode(issue.code()),
                0));
      }
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
      } else if (issue.code().isEmpty()) {
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

  /** 固定排查建议只依赖稳定代码，不插入外部异常文本。 */
  public static String hint(String code) {
    return switch (code) {
      case "SOURCE_ACCESS_DENIED" -> "检查运行用户的来源文件读取权限、macOS 隐私授权及临时目录写权限。";
      case "SOURCE_FILE_MISSING" -> "来源文件在读取时不可用；确认会话未被删除或移动后重试。";
      case "SOURCE_TEMP_IO_FAILED", "SOURCE_RESOURCE_CLOSE_FAILED" -> "检查系统临时目录的权限和可用空间后重试。";
      case "SOURCE_IO_FAILED" -> "检查来源文件可读性、临时目录权限和可用磁盘空间。";
      case "CODEX_HISTORY_READER_INCOMPLETE" -> "Codex 继承历史读取不完整；查看同次扫描的行号诊断，确认原始 JSONL 完整。";
      case "CODEX_HISTORY_BOUNDARY_INVALID" -> "Codex 子会话标记的继承历史边界不在有效记录范围内；检查导出文件是否完整。";
      case "CODEX_HISTORY_PARENT_CONFLICT" -> "Codex 子会话的父会话标识互相冲突；请保留原始文件并反馈 Codex 版本和此错误码。";
      case "CODEX_HISTORY_ORDINAL_INVALID" -> "Codex 子会话记录序号缺失、不连续或重复；检查文件是否被截断、拼接或重新排序。";
      case "CODEX_HISTORY_USAGE_UNSUPPORTED" -> "Codex 子会话继承历史中的累计用量归属无法验证；请反馈 Codex 版本和此错误码。";
      case "SOURCE_RETRYABLE_INCOMPLETE" -> "读取未完成；等待会话文件停止写入后重试。";
      case "BUFFER_OVERFLOW" -> "单条来源记录超出解析缓冲上限；反馈来源和行号，不必提供正文。";
      case "INVALID_UTF8" -> "来源文件不是有效的 UTF-8；检查文件是否损坏或被其他编码保存。";
      case "SOURCE_FATAL", "SOURCE_PARSER_EXCEPTION" -> "查看同次扫描的具体来源诊断；若复现，请反馈 scanLogId、来源和错误码。";
      case "SCAN_ARTIFACT_DIRECTORY_FAILED" -> "检查制品输出目录是否可写、是否被普通文件占用，以及磁盘可用空间。";
      case "SCAN_SCHEMA_INIT_FAILED",
          "SCAN_LOG_START_FAILED",
          "SCAN_FINGERPRINT_LOAD_FAILED",
          "SCAN_INDEX_PREPARE_FAILED",
          "SCAN_LOG_FINISH_FAILED" ->
          "检查当前版本的索引目录及 SQLite 数据库是否可读写、是否被其他进程占用。";
      case "SCAN_JVM_OUT_OF_MEMORY" -> "扫描因 JVM 内存不足中止；检查 JVM 堆配置和机器可用内存，可先按单一来源复现。";
      case "SCAN_JVM_STACK_OVERFLOW" -> "扫描因 JVM 栈溢出中止；请反馈来源、阶段和代码栈帧。";
      case "SCAN_JVM_LINKAGE_ERROR" -> "检查发行包是否完整、是否为 Apple Silicon macOS 版本，以及启动器使用的 JDK 是否正确。";
      case "SCAN_JVM_FATAL" -> "扫描异常中止；请反馈错误码、异常类型和代码栈帧。";
      default -> "";
    };
  }

  private static String safeCode(String code) {
    String detail = code.startsWith("BAD_JSON:") ? code.substring("BAD_JSON:".length()) : code;
    return detail.matches("[A-Z][A-Z0-9_]{0,79}") ? detail : "SOURCE_ERROR";
  }
}
