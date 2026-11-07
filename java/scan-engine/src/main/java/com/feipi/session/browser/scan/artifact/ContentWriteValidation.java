package com.feipi.session.browser.scan.artifact;

import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import java.io.IOException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** 仅保留跨单元校验所需的标识和计数，不持有正文载荷或完整内容单元。 */
final class ContentWriteValidation {
  private final NormalizedContentHeader header;
  private final Map<String, Long> counts = new HashMap<>();
  private final Map<String, Long> sequenceOffsets = new HashMap<>();
  private final Set<String> callIds = new HashSet<>();
  private final Set<String> catalogKeys = new HashSet<>();
  private final Set<String> toolIds = new HashSet<>();
  private final Set<String> callReferences = new HashSet<>();
  private final Set<String> toolReferences = new HashSet<>();
  private long unitIndex;
  private long callIndex = -1;

  ContentWriteValidation(NormalizedContentHeader header) {
    this.header = header;
    header.totals().keySet().forEach(key -> counts.put(key, 0L));
  }

  void accept(NormalizedContentUnit unit) throws IOException {
    if (unit.unitIndex() != unitIndex++) {
      throw new IOException("non-contiguous content unitIndex");
    }
    add("calls", unit.calls().size());
    add("toolExecutions", unit.toolExecutions().size());
    add("diagnostics", unit.diagnostics().size());
    add("sourceFiles", unit.sourceFiles().size());
    add("sourceUnitCatalog", unit.sourceUnitCatalog().size());
    for (var call : unit.calls()) {
      if (!callIds.add(call.callId())) {
        throw new IOException("duplicate global callId");
      }
      if (call.callIndex() <= callIndex) {
        throw new IOException("global callIndex is not increasing");
      }
      callIndex = call.callIndex();
      call.parentCallId().ifPresent(callReferences::add);
      call.parentToolCallId().ifPresent(toolReferences::add);
      toolReferences.addAll(call.response().toolCallIds());
      toolReferences.addAll(call.request().toolResultIds());
    }
    for (var tool : unit.toolExecutions()) {
      if (!toolIds.add(tool.toolCallId())) {
        throw new IOException("duplicate global toolCallId");
      }
      callReferences.add(tool.declaredByCallId());
      tool.resultConsumedByCallId().ifPresent(callReferences::add);
    }
    for (var entry : unit.sourceUnitCatalog().entrySet()) {
      if (!catalogKeys.add(entry.getKey())) {
        throw new IOException("duplicate source catalog key");
      }
      if (!entry.getKey().equals(entry.getValue().unitKey())) {
        throw new IOException("catalog key mismatch");
      }
    }
    for (var chunk : unit.sourceUnitSequences()) {
      long expected = sequenceOffsets.getOrDefault(chunk.name(), 0L);
      if (expected != chunk.offset()) {
        throw new IOException("non-contiguous source sequence offset");
      }
      sequenceOffsets.put(chunk.name(), Math.addExact(expected, chunk.keys().size()));
      add("sourceUnitSequenceEntries", chunk.keys().size());
    }
  }

  void finish() throws IOException {
    if (unitIndex == 0 || !counts.equals(header.totals())) {
      throw new IOException("content totals mismatch");
    }
    if (!callIds.containsAll(callReferences) || !toolIds.containsAll(toolReferences)) {
      throw new IOException("unresolved strong content reference");
    }
  }

  private void add(String key, long value) throws IOException {
    long count = Math.addExact(counts.get(key), value);
    if (count > header.totals().get(key)) {
      throw new IOException("content exceeds declared " + key);
    }
    counts.put(key, count);
  }
}
