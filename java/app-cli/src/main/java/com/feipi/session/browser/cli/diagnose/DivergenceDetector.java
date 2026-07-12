package com.feipi.session.browser.cli.diagnose;

/** 相邻层确定性比较，检测首个可证明的分歧。 */
final class DivergenceDetector {

  private DivergenceDetector() {}

  /**
   * 比较各层数据，检测首个分歧。
   *
   * <p>规则：只比较实际存在的相邻层。任一层不可用时返回 UNAVAILABLE，不猜测根因。
   *
   * @param raw 原始统计
   * @param normalization 归一化摘要
   * @param projection 投影摘要
   * @param sourceSubagentCount 源层发现的 subagent 文件数
   * @return 分歧检测结果
   */
  static DiagnoseOutputModel.DivergenceInfo detect(
      DiagnoseOutputModel.RawInfo raw,
      DiagnoseOutputModel.NormalizationInfo normalization,
      DiagnoseOutputModel.ProjectionInfo projection,
      int sourceSubagentCount) {

    // 1. raw → normalization：raw 有 assistant 消息但 normalization 没有 call
    if ("OBSERVED".equals(raw.status()) && "OBSERVED".equals(normalization.status())) {
      if (raw.assistantMessages() > 0 && normalization.callCount() == 0) {
        return buildDivergence(
            "raw→normalization",
            "MISMATCH",
            "raw 有 " + raw.assistantMessages() + " 个 assistant 消息，归一化应产生至少 1 个 call",
            "normalization.callCount = 0",
            "检查 EventClassifier 是否正确识别了 assistant 事件",
            "检查 EventClassifier.classify() 和 CallBuilder.buildCalls()");
      }
    }

    // 2. normalization → projection：call 数量一致性
    if ("OBSERVED".equals(normalization.status()) && "OBSERVED".equals(projection.status())) {
      if (normalization.callCount() != projection.totalCallCount()) {
        return buildDivergence(
            "normalization→projection",
            "MISMATCH",
            "normalization.callCount = " + normalization.callCount(),
            "projection.totalCallCount = " + projection.totalCallCount(),
            "投影层从归一化 call 列表派生，数量应一致",
            "检查 ProjectionSummarizer 是否正确遍历了 calls 列表");
      }
    }

    // 3. source → raw：源层有文件但 raw 层没有事件
    if ("OBSERVED".equals(raw.status())) {
      if (raw.totalEvents() == 0 && !"UNAVAILABLE".equals(raw.status())) {
        return buildDivergence(
            "source→raw",
            "MISMATCH",
            "源文件存在，应能解析出事件",
            "raw.totalEvents = 0",
            "JSONL 文件可能为空或格式不兼容",
            "检查 JSONL 文件内容格式是否符合 Claude Code 规范");
      }
    }

    // 4. source → projection：subagent 数量一致性
    if (sourceSubagentCount > 0 && "OBSERVED".equals(projection.status())) {
      if (projection.detectedSubagents() == 0) {
        return buildDivergence(
            "source→projection",
            "MISMATCH",
            "source 发现 " + sourceSubagentCount + " 个 subagent 文件",
            "projection.detectedSubagents = 0",
            "subagent 文件存在但投影未识别",
            "检查 CallBuilder 是否将 subagent records 标记为 SUBAGENT scope");
      }
    }

    // 5. 检查 UNAVAILABLE 层
    if ("UNAVAILABLE".equals(raw.status())) {
      return buildDivergence(
          "source→raw",
          "UNAVAILABLE",
          "源文件存在时应能解析",
          "raw status = UNAVAILABLE",
          "源解析返回空结果",
          "检查源文件格式和 SourceAdapter.parse() 日志");
    }

    if ("UNAVAILABLE".equals(normalization.status())) {
      return buildDivergence(
          "raw→normalization",
          "UNAVAILABLE",
          "raw 数据存在时应能归一化",
          "normalization status = UNAVAILABLE",
          "归一化未执行或失败",
          "检查 NormalizationEngine.normalize() 调用参数");
    }

    if ("UNAVAILABLE".equals(projection.status())) {
      return buildDivergence(
          "normalization→projection",
          "UNAVAILABLE",
          "归一化数据存在时应能投影",
          "projection status = UNAVAILABLE",
          "投影未执行",
          "检查 ProjectionSummarizer 调用");
    }

    // 无分歧
    return new DiagnoseOutputModel.DivergenceInfo("MATCH", null);
  }

  private static DiagnoseOutputModel.DivergenceInfo buildDivergence(
      String stage,
      String status,
      String expected,
      String observed,
      String evidence,
      String nextInspection) {
    return new DiagnoseOutputModel.DivergenceInfo(
        status,
        new DiagnoseOutputModel.FirstDivergence(
            stage, status, expected, observed, evidence, nextInspection));
  }
}
