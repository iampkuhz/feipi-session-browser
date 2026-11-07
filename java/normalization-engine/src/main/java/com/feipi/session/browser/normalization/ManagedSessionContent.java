package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;

/** 按已完成的全局计划逐调用重放正文，不拥有源序列。 */
final class ManagedSessionContent implements NormalizedSessionContent {
  private final ManagedNormalizationPlan plan;
  private static final long UNIT_BYTES = 1024 * 1024;

  /**
   * 创建只借用计划与源生命周期的内容。
   *
   * @param plan 完整的无正文全局计划
   */
  ManagedSessionContent(ManagedNormalizationPlan plan) {
    this.plan = plan;
  }

  @Override
  public NormalizedContentHeader header() {
    return plan.header;
  }

  @Override
  public ContentCursor openCursor() {
    return new Cursor();
  }

  private SourceRecord read(long ordinal) throws IOException {
    try (var cursor = plan.records.openCursor(ordinal)) {
      return cursor.next();
    }
  }

  private NormalizedCall call(ManagedNormalizationPlan.Frame frame) throws IOException {
    List<Map<String, Object>> units = new ArrayList<>();
    long previous = -1;
    SourceRecord record = null;
    for (var ref : frame.units) {
      if (record == null || previous != ref.ordinal()) {
        record = read(ref.ordinal());
        previous = ref.ordinal();
      }
      Map<String, Object> unit = new LinkedHashMap<>();
      if (ref.toolIndex() >= 0) {
        var tool = record.toolCalls().get(ref.toolIndex());
        unit.put("type", "tool_use");
        unit.put("role", "assistant");
        unit.put("text", "");
        unit.put("id", tool.toolCallId());
        unit.put("name", tool.name());
        unit.put("input", tool.input());
      } else {
        unit.put("type", record.eventType());
        unit.put("role", ref.role());
        unit.put("text", record.content());
        if (record.metaContext()) unit.put("isMeta", true);
        record.toolUseId().ifPresent(id -> unit.put("tool_call_id", id));
      }
      units.add(Map.copyOf(unit));
    }
    return new NormalizedCall(
        frame.id,
        frame.index,
        "C" + frame.index,
        frame.scope,
        frame.parent,
        frame.parentTool,
        frame.turn,
        frame.model,
        frame.timestamp,
        frame.usage,
        new NormalizedCallRequest(frame.results),
        new NormalizedCallResponse(
            frame.fact.tools().stream().map(ManagedNormalizationPlan.ToolIdentity::id).toList()),
        List.of(),
        units,
        Map.of(),
        new LinkedHashMap<String, Object>(frame.provenance),
        frame.subagent,
        frame.parentToolName);
  }

  private NormalizedToolExecution tool(ManagedNormalizationPlan.ToolRef ref) throws IOException {
    String id;
    String name;
    Optional<String> error;
    var scope = ref.scope();
    var subagent = ref.subagent();
    if (ref.index() < 0) {
      SourceRecord record = read(ref.fact().ordinal());
      id = record.callId().orElseThrow();
      name = record.toolName().orElseThrow();
      Long errorOrdinal = plan.errors.get(id);
      error = record.toolError();
      if (error.isEmpty() && errorOrdinal != null) error = read(errorOrdinal).toolError();
      scope = CallBuilder.callScope(record);
      subagent = CallBuilder.toolExecutionSubagentId(record);
    } else {
      var identity = ref.fact().tools().get(ref.index());
      id = identity.id();
      name = identity.name();
      Long errorOrdinal = plan.errors.get(id);
      error = errorOrdinal == null ? Optional.empty() : read(errorOrdinal).toolError();
    }
    return new NormalizedToolExecution(
        id,
        name,
        scope,
        ref.owner(),
        Optional.ofNullable(plan.consumers.get(id)),
        error,
        Optional.empty(),
        0L,
        List.of(),
        subagent);
  }

  private static long payloadBytes(NormalizedCall call) {
    long bytes = 0;
    for (var unit : call.sourceUnits()) {
      for (Object value : unit.values()) if (value instanceof String text) bytes += utf8Bytes(text);
    }
    return bytes;
  }

  private static long utf8Bytes(String text) {
    long length = 0;
    for (int i = 0; i < text.length(); i++) {
      char c = text.charAt(i);
      if (c < 0x80) length++;
      else if (c < 0x800) length += 2;
      else if (Character.isHighSurrogate(c)
          && i + 1 < text.length()
          && Character.isLowSurrogate(text.charAt(i + 1))) {
        length += 4;
        i++;
      } else length += Character.isSurrogate(c) ? 1 : 3;
    }
    return length;
  }

  /** 每个游标仅保留当前 byte-target unit 与最多一个待输出调用。 */
  private final class Cursor implements ContentCursor {
    private int callIndex;
    private int toolIndex;
    private int diagnosticIndex;
    private int fileIndex;
    private final Iterator<Map.Entry<String, SourceUnitCatalogEntry>> catalog =
        plan.catalog.entrySet().iterator();
    private long unitIndex;
    private boolean closed;
    private NormalizedCall pending;

    @Override
    public boolean hasNext() throws IOException {
      checkOpen();
      return pending != null
          || callIndex < plan.frames.size()
          || toolIndex < plan.tools.size()
          || diagnosticIndex < plan.diagnostics.size()
          || fileIndex < plan.sourceFiles.size()
          || catalog.hasNext();
    }

    @Override
    public NormalizedContentUnit next() throws IOException {
      if (!hasNext()) throw new NoSuchElementException();
      var calls = new ArrayList<NormalizedCall>();
      long bytes = 0;
      while (pending != null || callIndex < plan.frames.size()) {
        NormalizedCall current = pending != null ? pending : call(plan.frames.get(callIndex++));
        pending = null;
        long currentBytes = payloadBytes(current);
        if (!calls.isEmpty() && bytes + currentBytes > UNIT_BYTES) {
          pending = current;
          break;
        }
        calls.add(current);
        bytes += currentBytes;
        if (bytes >= UNIT_BYTES || calls.size() >= NormalizedConstants.MAX_COLLECTION_SIZE) break;
      }
      // 与调用分开生产，避免错误正文或目录把当前调用单元扩大。
      if (!calls.isEmpty())
        return new NormalizedContentUnit(
            unitIndex++, List.of(), calls, List.of(), List.of(), Map.of(), List.of());
      if (toolIndex < plan.tools.size())
        return new NormalizedContentUnit(
            unitIndex++,
            List.of(),
            List.of(),
            List.of(tool(plan.tools.get(toolIndex++))),
            List.of(),
            Map.of(),
            List.of());
      if (diagnosticIndex < plan.diagnostics.size())
        return new NormalizedContentUnit(
            unitIndex++,
            List.of(),
            List.of(),
            List.of(),
            List.of(plan.diagnostics.get(diagnosticIndex++)),
            Map.of(),
            List.of());
      if (fileIndex < plan.sourceFiles.size())
        return new NormalizedContentUnit(
            unitIndex++,
            List.of(plan.sourceFiles.get(fileIndex++)),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            List.of());
      var entry = catalog.next();
      return new NormalizedContentUnit(
          unitIndex++,
          List.of(),
          List.of(),
          List.of(),
          List.of(),
          Map.of(entry.getKey(), entry.getValue()),
          List.of());
    }

    private void checkOpen() throws IOException {
      if (closed) throw new IOException("content cursor is closed");
    }

    @Override
    public void close() {
      closed = true;
      pending = null;
    }
  }
}
