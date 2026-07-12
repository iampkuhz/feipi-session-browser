package com.feipi.session.browser.cli.diagnose;

import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 从 {@link SourceRecord} 列表生成原始结构统计。 */
final class RawSummarizer {

  private RawSummarizer() {}

  /**
   * 统计原始事件的结构信息。
   *
   * @param records 解析后的源记录列表
   * @param sourceErrors 解析阶段的错误信息
   * @return 原始统计
   */
  static DiagnoseOutputModel.RawInfo summarize(
      List<SourceRecord> records, List<String> sourceErrors) {
    if (records.isEmpty() && sourceErrors.isEmpty()) {
      return new DiagnoseOutputModel.RawInfo("UNAVAILABLE", 0, Map.of(), 0, 0, 0, 0, 0, List.of());
    }

    Map<String, Integer> eventTypeCounts = new LinkedHashMap<>();
    int assistantMessages = 0;
    int userMessages = 0;
    int toolUseCount = 0;
    int toolResultCount = 0;
    int parseErrors = 0;

    for (SourceRecord record : records) {
      String type = record.eventType();
      eventTypeCounts.merge(type, 1, Integer::sum);

      switch (type) {
        case "assistant" -> assistantMessages++;
        case "user" -> userMessages++;
        default -> {}
      }

      // tool_use 在 assistant 消息的 toolCalls 中
      toolUseCount += record.toolCalls().size();

      // tool_result 在 user 消息中有 toolUseId
      if (record.toolUseId().isPresent()) {
        toolResultCount++;
      }

      // 未知事件类型计为 parse error
      if ("unknown".equals(type)) {
        parseErrors++;
      }
    }

    String status = records.isEmpty() && !sourceErrors.isEmpty() ? "ERROR" : "OBSERVED";

    return new DiagnoseOutputModel.RawInfo(
        status,
        records.size(),
        Map.copyOf(eventTypeCounts),
        assistantMessages,
        userMessages,
        toolUseCount,
        toolResultCount,
        parseErrors,
        List.copyOf(sourceErrors));
  }
}
