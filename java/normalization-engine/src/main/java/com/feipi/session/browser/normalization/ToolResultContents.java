package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

/** 实际结果独立于消费边保留；目录键使用源位置而非可能重复的裸工具 ID。 */
final class ToolResultContents {
  private static final Pattern BLOCK_INDEX = Pattern.compile("#event\\[\\d+\\]\\[(\\d+)\\]$");

  private ToolResultContents() {}

  static boolean isResult(SourceRecord record) {
    return "tool_result".equals(record.eventType()) && record.toolUseId().isPresent();
  }

  static SourceUnitCatalogEntry entry(SourceRecord record, long ordinal) {
    String locator = record.locator();
    int suffix = locator.lastIndexOf("#event[");
    String path = suffix < 0 ? locator : locator.substring(0, suffix);
    var block = BLOCK_INDEX.matcher(locator);
    int partIndex = block.find() ? Integer.parseInt(block.group(1)) : 0;
    String id = record.toolUseId().orElseThrow();
    return new SourceUnitCatalogEntry(
        "tool-result:" + ordinal + ":" + locator,
        path,
        locator,
        "tool_result",
        "",
        SourceUnitDirection.REQUEST,
        record.eventIndex(),
        partIndex,
        ByteRange.empty(),
        "",
        record.timestamp(),
        Optional.of(id),
        50,
        Optional.empty(),
        Optional.of(record.content()),
        Map.of("type", "tool_result", "tool_call_id", id),
        Optional.empty(),
        Optional.empty(),
        List.of());
  }
}
