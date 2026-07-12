package com.feipi.session.browser.cli.diagnose;

import java.util.Map;

/** 人类可读的紧凑表格渲染器。 */
public final class HumanRenderer {

  private HumanRenderer() {}

  /**
   * 将诊断输出渲染为人类可读文本。
   *
   * @param output 诊断输出
   * @return 紧凑的文本报告
   */
  public static String render(DiagnoseOutputModel.DiagnoseOutput output) {
    StringBuilder sb = new StringBuilder();

    // 标题
    sb.append("=== Session Diagnose ===\n");
    sb.append("agent:       ").append(output.request().agent()).append('\n');
    sb.append("session-id:  ").append(output.request().sessionId()).append('\n');
    sb.append("source-dir:  ").append(output.request().sourceDir()).append('\n');
    sb.append('\n');

    // 源定位
    renderSource(sb, output.source());
    sb.append('\n');

    // 原始解析
    renderRaw(sb, output.raw());
    sb.append('\n');

    // 归一化
    renderNormalization(sb, output.normalization());
    sb.append('\n');

    // 投影
    renderProjection(sb, output.projection());
    sb.append('\n');

    // 分歧检测
    renderDivergence(sb, output.divergence());
    sb.append('\n');

    // 各阶段耗时
    sb.append("--- Timing ---\n");
    sb.append(
        String.format(
            "  total: %dms (source: %dms, raw: %dms, norm: %dms, proj: %dms)%n",
            output.timing().totalMs(),
            output.timing().sourceMs(),
            output.timing().rawMs(),
            output.timing().normalizationMs(),
            output.timing().projectionMs()));

    // 警告信息
    if (!output.warnings().isEmpty()) {
      sb.append('\n').append("--- Warnings ---\n");
      for (String w : output.warnings()) {
        sb.append("  ! ").append(w).append('\n');
      }
    }

    return sb.toString();
  }

  private static void renderSource(StringBuilder sb, DiagnoseOutputModel.SourceInfo source) {
    sb.append("--- Source ---\n");
    sb.append("  status:          ").append(source.status()).append('\n');
    if (!source.transcriptPath().isEmpty()) {
      sb.append("  transcript:        ").append(source.transcriptPath());
      sb.append(" (").append(source.transcriptSizeBytes()).append(" bytes)\n");
    }
    if (!source.subagentsDir().isEmpty()) {
      sb.append("  subagents-dir:     ").append(source.subagentsDir()).append('\n');
      sb.append("  subagent-files:    ").append(source.subagentFileCount()).append('\n');
      for (DiagnoseOutputModel.SubagentFileInfo f : source.subagentFiles()) {
        sb.append("    - ")
            .append(f.fileName())
            .append(" (")
            .append(f.sizeBytes())
            .append(" bytes, meta: ")
            .append(f.metaStatus())
            .append(")\n");
      }
    }
    sb.append("  meta:              ").append(source.metaStatus()).append('\n');
    if (!source.meta().isEmpty()) {
      for (Map.Entry<String, String> e : source.meta().entrySet()) {
        sb.append("    ").append(e.getKey()).append(": ").append(e.getValue()).append('\n');
      }
    }
  }

  private static void renderRaw(StringBuilder sb, DiagnoseOutputModel.RawInfo raw) {
    sb.append("--- Raw ---\n");
    sb.append("  status:            ").append(raw.status()).append('\n');
    sb.append("  total-events:      ").append(raw.totalEvents()).append('\n');
    if (!raw.eventTypeCounts().isEmpty()) {
      sb.append("  event-type-counts:\n");
      for (Map.Entry<String, Integer> e : raw.eventTypeCounts().entrySet()) {
        sb.append("    ").append(e.getKey()).append(": ").append(e.getValue()).append('\n');
      }
    }
    sb.append("  assistant-messages:").append(" ").append(raw.assistantMessages()).append('\n');
    sb.append("  user-messages:     ").append(raw.userMessages()).append('\n');
    sb.append("  tool-use-count:    ").append(raw.toolUseCount()).append('\n');
    sb.append("  tool-result-count: ").append(raw.toolResultCount()).append('\n');
    sb.append("  parse-errors:      ").append(raw.parseErrors()).append('\n');
    for (String err : raw.sourceErrors()) {
      sb.append("  ! ").append(err).append('\n');
    }
  }

  private static void renderNormalization(
      StringBuilder sb, DiagnoseOutputModel.NormalizationInfo norm) {
    sb.append("--- Normalization ---\n");
    sb.append("  status:            ").append(norm.status()).append('\n');
    if ("OBSERVED".equals(norm.status())) {
      sb.append("  schema-version:    ").append(norm.schemaVersion()).append('\n');
      sb.append("  call-count:        ")
          .append(norm.callCount())
          .append(" (main: ")
          .append(norm.mainCallCount())
          .append(", subagent: ")
          .append(norm.subagentCallCount())
          .append(")\n");
      sb.append("  tool-executions:   ").append(norm.toolExecutionCount()).append('\n');
      sb.append("  diagnostics:       ").append(norm.diagnosticCount()).append('\n');
      sb.append("  total-tokens:      ").append(norm.totalTokens()).append('\n');
      sb.append("  source-files:      ").append(norm.sourceFileCount()).append('\n');
    }
  }

  private static void renderProjection(StringBuilder sb, DiagnoseOutputModel.ProjectionInfo proj) {
    sb.append("--- Projection ---\n");
    sb.append("  status:            ").append(proj.status()).append('\n');
    if ("OBSERVED".equals(proj.status())) {
      sb.append("  detected-agents:   ").append(proj.detectedAgents()).append('\n');
      sb.append("  detected-subagents:").append(" ").append(proj.detectedSubagents()).append('\n');
      sb.append("  main-tool-calls:   ").append(proj.mainToolCallCount()).append('\n');
      sb.append("  subagent-tool-calls: ").append(proj.subagentToolCallCount()).append('\n');
      sb.append("  total-calls:       ").append(proj.totalCallCount()).append('\n');
    }
  }

  private static void renderDivergence(StringBuilder sb, DiagnoseOutputModel.DivergenceInfo div) {
    sb.append("--- Divergence ---\n");
    sb.append("  status:            ").append(div.status()).append('\n');
    DiagnoseOutputModel.FirstDivergence first = div.first();
    if (first != null) {
      sb.append("  first:\n");
      sb.append("    stage:           ").append(first.stage()).append('\n');
      sb.append("    expected:        ").append(first.expected()).append('\n');
      sb.append("    observed:        ").append(first.observed()).append('\n');
      sb.append("    evidence:        ").append(first.evidence()).append('\n');
      sb.append("    next-inspection: ").append(first.nextInspection()).append('\n');
    }
  }
}
