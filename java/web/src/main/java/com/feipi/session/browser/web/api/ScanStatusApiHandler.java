package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import io.javalin.http.Context;
import java.util.List;

/** 最新扫描运行状态，不与已发布数据 generation/cache 绑定。 */
public final class ScanStatusApiHandler {
  private final QueryCompositionRoot queryRoot;

  /**
   * 创建只读状态处理器。
   *
   * @param queryRoot 当前个人索引的应用查询根
   */
  public ScanStatusApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = java.util.Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
  }

  /**
   * 返回最新扫描的安全状态，不泄漏本机会话键、路径、preview 或异常原文。
   *
   * @param context HTTP 上下文
   */
  public void handle(Context context) {
    context.header("Cache-Control", "no-store");
    var latest = queryRoot.latestScan();
    if (latest.isEmpty()) {
      context.json(
          new Response(
              "unknown",
              0,
              0,
              0,
              false,
              List.of(),
              "No scan status is recorded; current data coverage is unknown.",
              retryCommand()));
      return;
    }
    var status = latest.get();
    var reasons =
        status.failures().stream()
            .map(
                failure ->
                    new Reason(
                        failure.source(),
                        failure.phase(),
                        failure.code(),
                        failure.line(),
                        explanation(failure.code())))
            .toList();
    String message =
        switch (status.status()) {
          case "failure" ->
              status.publishedDataAvailable()
                  ? "Latest scan failed. Previous successfully published data is still displayed; this failed scan published no partial results."
                  : "Latest scan failed. No successfully published index is available; this failed scan published no partial results.";
          case "running" ->
              "Scan is running. Previously published data remains unchanged until atomic publication.";
          case "success" -> "Latest scan completed and its valid data was published atomically.";
          default -> "Scan status is unknown.";
        };
    context.json(
        new Response(
            status.status(),
            status.processedCount(),
            "success".equals(status.status()) ? status.processedCount() : 0,
            status.errorCount(),
            status.publishedDataAvailable(),
            reasons,
            message,
            retryCommand()));
  }

  private static String explanation(String code) {
    return switch (code) {
      case "BUFFER_OVERFLOW" ->
          "Source parsing reached its bounded buffer limit; source content was not fully processed.";
      case "NORMALIZED_CALL_LIMIT_EXCEEDED" ->
          "The normalized session exceeds the supported 10,000-call limit. Large-source support has not been restored by this failed scan.";
      case "LEGACY_SCAN_FAILURE" ->
          "This older scan failed before detailed failure reasons were recorded.";
      default ->
          "The scan could not complete. Resolve the reported stage/code before retrying the same input.";
    };
  }

  private static String retryCommand() {
    return "./scripts/session-browser.sh scan --incremental --index-dir <same-index-directory>";
  }

  /**
   * 仅含安全诊断定位字段的原因。
   *
   * @param source 源适配器标识
   * @param phase 失败阶段
   * @param code 稳定错误代码
   * @param line 源行号，未知为零
   * @param explanation 固定安全说明，不包含源原文
   */
  record Reason(String source, String phase, String code, int line, String explanation) {}

  /**
   * 扫描状态响应，候选处理数量不等于全索引会话数量。
   *
   * @param status 最新扫描状态
   * @param processedCount 本次已经处理的候选项数量
   * @param publishedProcessedCount 本次已处理且成功发布的候选项数量，失败为零
   * @param errorCount 失败候选或阶段问题数量，不等同于诊断明细条数
   * @param publishedDataAvailable 是否仍有有效已发布数据
   * @param reasons 安全错误原因
   * @param message 状态说明
   * @param retryCommand 用户可以在原索引目录执行的既有重试命令
   */
  record Response(
      String status,
      int processedCount,
      int publishedProcessedCount,
      int errorCount,
      boolean publishedDataAvailable,
      List<Reason> reasons,
      String message,
      String retryCommand) {}
}
