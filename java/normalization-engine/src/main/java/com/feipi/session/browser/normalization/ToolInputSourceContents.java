package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** 无模型归属的真实工具槽位；不补调用、响应引用或镜像。 */
final class ToolInputSourceContents {
  private ToolInputSourceContents() {}

  static SourceUnitCatalogEntry entry(SourceRecord record, long ordinal, int slot) {
    var tool = record.toolCalls().get(slot);
    String locator = record.locator();
    int suffix = locator.lastIndexOf("#event[");
    String path = suffix < 0 ? locator : locator.substring(0, suffix);
    return new SourceUnitCatalogEntry(
        "tool-input:" + ordinal + ":" + slot + ":" + locator,
        path,
        locator,
        "tool_use",
        "independent_tool_input.v1",
        SourceUnitDirection.RESPONSE,
        record.eventIndex(),
        slot,
        ByteRange.empty(),
        "",
        record.timestamp(),
        Optional.of(tool.toolCallId()),
        50,
        Optional.empty(),
        Optional.empty(),
        Map.of(
            "type",
            "tool_use",
            "id",
            tool.toolCallId(),
            "name",
            tool.name(),
            "input",
            tool.input(),
            "independent",
            Map.of(
                "ordinal", Long.toString(ordinal),
                "slot", Integer.toString(slot),
                "scope", CallBuilder.callScope(record).getValue(),
                "subagent", CallBuilder.toolExecutionSubagentId(record).orElse(""))),
        Optional.empty(),
        Optional.empty(),
        List.of());
  }
}
