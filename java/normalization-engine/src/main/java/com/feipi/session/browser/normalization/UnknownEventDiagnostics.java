package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 聚合同一源内的未知事件警告；不截断、不改变 adapter 的解析诊断。 */
final class UnknownEventDiagnostics {
  private UnknownEventDiagnostics() {}

  static List<Map<String, Object>> collect(NormalizedAgent agent, List<SourceRecord> records) {
    Collector collector = new Collector(agent);
    records.forEach(collector::accept);
    return collector.diagnostics();
  }

  /** 只保留未知分组标量，不保留源记录或正文。 */
  static final class Collector {
    private final NormalizedAgent agent;
    private final Map<Key, Group> groups = new LinkedHashMap<>();

    Collector(NormalizedAgent agent) {
      this.agent = agent;
    }

    void accept(SourceRecord record) {
      if (knownStructure(agent, record)) return;
      String subtype =
          agent == NormalizedAgent.CODEX && "event_msg".equals(record.eventType())
              ? record.turnId().orElse("")
              : "";
      String locator = record.locator();
      int eventSuffix = locator.lastIndexOf("#event[");
      String source = eventSuffix < 0 ? locator : locator.substring(0, eventSuffix);
      Key key = new Key(source, record.eventType(), subtype);
      groups.computeIfAbsent(key, ignored -> new Group(record, subtype)).accept(record);
    }

    List<Map<String, Object>> diagnostics() {
      return groups.values().stream().map(Group::diagnostic).toList();
    }
  }

  private static boolean knownStructure(NormalizedAgent agent, SourceRecord record) {
    if (agent != NormalizedAgent.CODEX) {
      return false;
    }
    return switch (record.eventType()) {
      case "session_meta", "turn_context" -> true;
      case "event_msg" ->
          switch (record.turnId().orElse("")) {
            case "user_message", "agent_message", "task_started", "token_count" -> true;
            default -> false;
          };
      default -> false;
    };
  }

  /**
   * 同源同类型的诊断分组键。
   *
   * @param source 稳定源定位符
   * @param type 源事件类型
   * @param subtype 已知来源携带的子类型，其余为空
   */
  private record Key(String source, String type, String subtype) {}

  /** 保留重复次数与首末源事件位置的累加器。 */
  private static final class Group {
    private final String type;
    private final String firstLocator;
    private final int firstEventIndex;
    private final String subtype;
    private String lastLocator;
    private int lastEventIndex;
    private int count;

    private Group(SourceRecord first, String subtype) {
      this.type = first.eventType();
      this.firstLocator = first.locator();
      this.firstEventIndex = first.eventIndex();
      this.subtype = subtype;
    }

    private void accept(SourceRecord record) {
      lastLocator = record.locator();
      lastEventIndex = record.eventIndex();
      count++;
    }

    private Map<String, Object> diagnostic() {
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("severity", "WARNING");
      result.put("issueType", "NON_OBJECT_SKIPPED");
      result.put("code", "NON_OBJECT_SKIPPED");
      result.put(
          "message", "Unknown event type: " + type + (subtype.isEmpty() ? "" : "." + subtype));
      // 历史字段兼容值；真正源位置由 locator / eventIndex 表达，不推断物理行。
      result.put("lineNo", 1);
      result.put("locator", firstLocator);
      result.put("occurrenceCount", count);
      result.put("firstEventIndex", firstEventIndex);
      result.put("lastEventIndex", lastEventIndex);
      result.put("firstLocator", firstLocator);
      result.put("lastLocator", lastLocator);
      result.put("positionUnit", "sourceEventIndex");
      return Map.copyOf(result);
    }
  }
}
