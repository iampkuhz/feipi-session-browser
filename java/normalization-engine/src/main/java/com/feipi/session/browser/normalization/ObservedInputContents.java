package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

/** 无模型调用时仍保留显式主会话输入，不把输入伪造成调用。 */
final class ObservedInputContents {
  private static final Pattern BLOCK_INDEX = Pattern.compile("#event\\[\\d+\\]\\[(\\d+)\\]$");

  private ObservedInputContents() {}

  static boolean isUser(SourceRecord record) {
    return record.messageRole().filter("user"::equals).isPresent()
        && !record.metaContext()
        && record.toolUseId().isEmpty()
        && record.relation().subagentId().isEmpty()
        && !record.locator().replace('\\', '/').contains("/subagents/");
  }

  static SourceUnitCatalogEntry entry(SourceRecord record) {
    String locator = record.locator();
    int suffix = locator.lastIndexOf("#event[");
    String path = suffix < 0 ? locator : locator.substring(0, suffix);
    var block = BLOCK_INDEX.matcher(locator);
    int partIndex = block.find() ? Integer.parseInt(block.group(1)) : 0;
    return new SourceUnitCatalogEntry(
        "observed-user:" + locator,
        path,
        locator,
        "user",
        "observed_user_message",
        SourceUnitDirection.REQUEST,
        record.eventIndex(),
        partIndex,
        ByteRange.empty(),
        "",
        record.timestamp(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.of(record.content()),
        Map.of("role", "user"),
        Optional.empty(),
        Optional.empty(),
        List.of());
  }
}
