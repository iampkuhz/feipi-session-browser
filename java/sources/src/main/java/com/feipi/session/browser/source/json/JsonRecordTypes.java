package com.feipi.session.browser.source.json;

import com.feipi.session.browser.source.spi.SourceAdapter.RecordKind;
import com.feipi.session.browser.source.spi.SourceId;
import java.util.Set;

/** 来源层共同维护已知记录类型，导入层不再复制格式白名单。 */
public final class JsonRecordTypes {
  private static final Set<String> CODEX =
      Set.of("session_meta", "response_item", "event_msg", "turn_context", "token_usage_record");
  private static final Set<String> MESSAGES = Set.of("user", "assistant");
  private static final Set<String> IGNORED =
      Set.of("workspace-directories", "runtime-config", "active-leaf");
  private static final Set<String> AUXILIARY =
      Set.of(
          "system",
          "summary",
          "progress",
          "file-history-snapshot",
          "queue-operation",
          "last-prompt",
          "custom-title",
          "tag",
          "agent-name",
          "pr-link",
          "mode",
          "permission-mode",
          "attachment");

  private JsonRecordTypes() {}

  /**
   * 根据来源及原始角色字段识别记录。
   *
   * @param source 来源标识
   * @param type 顶层类型
   * @param role 顶层角色
   * @param messageRole 包装消息角色
   * @return 严格入口可消费的来源识别结果
   */
  public static RecordKind classify(SourceId source, String type, String role, String messageRole) {
    if (CODEX.contains(type))
      return source == SourceId.CODEX ? RecordKind.TRANSCRIPT : RecordKind.FOREIGN;
    if (MESSAGES.contains(type))
      return source == SourceId.CODEX ? RecordKind.FOREIGN : RecordKind.TRANSCRIPT;
    if (type.isEmpty() && MESSAGES.contains(role))
      return source == SourceId.QODER ? RecordKind.TRANSCRIPT : RecordKind.FOREIGN;
    if (source == SourceId.CODEX) return RecordKind.UNKNOWN;
    if (IGNORED.contains(type)) return RecordKind.IGNORED_METADATA;
    if (source == SourceId.QODER) {
      if ("message".equals(type) && MESSAGES.contains(qoderType(type, role, messageRole)))
        return RecordKind.TRANSCRIPT;
      if ("tool_result".equals(type)) return RecordKind.AUXILIARY;
    }
    return AUXILIARY.contains(type) ? RecordKind.AUXILIARY : RecordKind.UNKNOWN;
  }

  /**
   * Qoder 主格式、cache 及 message 包装共用的事件类型解释。
   *
   * @param type 顶层类型
   * @param role 顶层角色
   * @param messageRole 包装消息角色
   * @return 源中性事件类型；顶层角色优先，未知包装保持原类型
   */
  public static String qoderType(String type, String role, String messageRole) {
    if (type.isEmpty()) return role.isEmpty() ? "unknown" : role;
    if (!"message".equals(type)) return type;
    String resolved = role.isEmpty() ? messageRole : role;
    return MESSAGES.contains(resolved) ? resolved : type;
  }

  /** 返回配置元数据是否应在扫描解析时排除，与导入识别共用同一类型表。 */
  public static boolean ignoredMetadata(String type) {
    return IGNORED.contains(type);
  }
}
