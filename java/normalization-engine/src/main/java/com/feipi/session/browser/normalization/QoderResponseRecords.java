package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Qoder 专用响应分片预处理。
 *
 * <p>Qoder 的同一次逻辑 assistant response 可能因流式分片被拆为多条 assistant 源记录（如文本分片、工具声明分片）， 它们共享相同的显式 {@code
 * message.id}（对应 {@link SourceRecord#responseMessageId()}）。本类将满足合并条件的连续 assistant
 * 记录合并为单条记录，使后续归一化产生正确数量的逻辑调用。
 *
 * <p>合并条件（全部满足）：
 *
 * <ul>
 *   <li>均为 {@code assistant} 类型
 *   <li>具有相同非空 responseMessageId（显式 message.id，不含 uuid/parentUuid 回退）
 *   <li>来自同一源文件（locator 去除事件索引后相同）
 *   <li>具有完全相同的 {@link SourceRecordRelation}（不仅 subagentId）
 *   <li>之间无 user 或 tool_result 输入边界
 *   <li>前一片无终止性 stop_reason（end_turn、tool_use、max_tokens）
 * </ul>
 *
 * <p>合并行为：
 *
 * <ul>
 *   <li>文本内容按顺序拼接
 *   <li>工具声明按 toolCallId 去重后合并，保持首次出现顺序；后片非空 input 覆盖前片空 input
 *   <li>usage 取各分片中的分量最大值（不叠加）
 *   <li>turnId 和 callId 使用稳定唯一标识，保证不同逻辑响应产生不同 round 且不碰撞
 *   <li>不伪造时间
 * </ul>
 *
 * <p>本类仅用于 QODER agent 的预处理，不影响 Claude/Codex 等其他 provider 的行为。
 */
final class QoderResponseRecords {

  private QoderResponseRecords() {}

  /** 生成唯一身份时使用的前缀，保证不与原始 ID 碰撞。 */
  private static final String ID_PREFIX = "qr$";

  /** 终止性 stop_reason 值，表示响应结束，后续不可合并。 */
  private static final java.util.Set<String> TERMINAL_STOP_REASONS =
      java.util.Set.of("end_turn", "tool_use", "max_tokens");

  /**
   * 合并满足条件的连续 assistant 分片。
   *
   * <p>非 assistant 记录和无法合并的记录保持原序不变。
   *
   * @param records 源记录列表
   * @return 合并后的记录列表
   */
  static List<SourceRecord> merge(List<SourceRecord> records) {
    if (records == null || records.size() <= 1) {
      return records;
    }
    List<SourceRecord> result = new ArrayList<>();
    List<SourceRecord> group = new ArrayList<>();
    String groupMessageId = null;
    String groupSourceKey = null;
    SourceRecordRelation groupRelation = null;
    // 用于生成唯一身份的计数器
    Map<String, Integer> identityUsageCount = new LinkedHashMap<>();

    for (SourceRecord record : records) {
      if ("assistant".equals(record.eventType())) {
        Optional<String> msgId = record.responseMessageId();
        String sourceKey = sourceFileKey(record.locator());
        SourceRecordRelation relation =
            record.relation() != null ? record.relation() : SourceRecordRelation.empty();

        if (msgId.isEmpty() || msgId.get().isBlank()) {
          // 无显式 message.id，不参与合并，但需要分配唯一身份
          flushGroup(result, group, identityUsageCount);
          group = new ArrayList<>();
          groupMessageId = null;
          groupSourceKey = null;
          groupRelation = null;
          result.add(ensureUniqueIdentity(record, identityUsageCount));
          continue;
        }

        String mid = msgId.get();
        boolean canMerge =
            !group.isEmpty()
                && mid.equals(groupMessageId)
                && sourceKey.equals(groupSourceKey)
                && relation.equals(groupRelation);

        if (canMerge) {
          group.add(record);
          // 检查当前片是否有终止性 stop_reason
          if (hasTerminalStopReason(record)) {
            flushGroup(result, group, identityUsageCount);
            group = new ArrayList<>();
            groupMessageId = null;
            groupSourceKey = null;
            groupRelation = null;
          }
        } else {
          flushGroup(result, group, identityUsageCount);
          group = new ArrayList<>();
          group.add(record);
          groupMessageId = mid;
          groupSourceKey = sourceKey;
          groupRelation = relation;
          // 检查单片是否有终止性 stop_reason
          if (hasTerminalStopReason(record)) {
            flushGroup(result, group, identityUsageCount);
            group = new ArrayList<>();
            groupMessageId = null;
            groupSourceKey = null;
            groupRelation = null;
          }
        }
      } else {
        // 非 assistant 记录终止当前组
        flushGroup(result, group, identityUsageCount);
        group = new ArrayList<>();
        groupMessageId = null;
        groupSourceKey = null;
        groupRelation = null;
        result.add(record);
      }
    }
    flushGroup(result, group, identityUsageCount);
    return List.copyOf(result);
  }

  /**
   * 从 locator 提取源文件身份。
   *
   * <p>去除 "#event[" 及之后的部分，保留文件名。例如 "synthetic.jsonl#event[0]" → "synthetic.jsonl"。
   */
  private static String sourceFileKey(String locator) {
    int hashIndex = locator.lastIndexOf("#event[");
    return hashIndex >= 0 ? locator.substring(0, hashIndex) : locator;
  }

  private static boolean hasTerminalStopReason(SourceRecord record) {
    return record.responseStopReason().filter(TERMINAL_STOP_REASONS::contains).isPresent();
  }

  private static void flushGroup(
      List<SourceRecord> result,
      List<SourceRecord> group,
      Map<String, Integer> identityUsageCount) {
    if (group.isEmpty()) {
      return;
    }
    if (group.size() == 1) {
      SourceRecord single = group.get(0);
      result.add(ensureUniqueIdentity(single, identityUsageCount));
    } else {
      result.add(mergeGroup(group, identityUsageCount));
    }
  }

  /**
   * 为记录分配唯一 turnId 和 callId。
   *
   * <p>使用 "qr$" 前缀 + 原始 ID + "$" + 计数器，保证与所有原始 ID 不碰撞且可追溯。 无显式 responseMessageId 时使用 locator 作为基础。
   */
  private static SourceRecord ensureUniqueIdentity(
      SourceRecord record, Map<String, Integer> identityUsageCount) {
    Optional<String> msgId = record.responseMessageId();
    String baseId;
    if (msgId.isEmpty() || msgId.get().isBlank()) {
      // 无显式 message.id，使用 locator 作为基础
      baseId = sourceFileKey(record.locator()) + ":e" + record.eventIndex();
    } else {
      baseId = msgId.get();
    }
    int count = identityUsageCount.merge(baseId, 1, Integer::sum);
    String uniqueId = ID_PREFIX + baseId + "$" + count;
    return withTurnIdAndCallId(record, uniqueId, uniqueId);
  }

  private static SourceRecord withTurnIdAndCallId(
      SourceRecord record, String newTurnId, String newCallId) {
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        record.eventType(),
        Optional.of(newCallId),
        record.model(),
        record.timestamp(),
        Optional.of(newTurnId),
        record.usage(),
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        record.relation(),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason());
  }

  private static SourceRecord mergeGroup(
      List<SourceRecord> group, Map<String, Integer> identityUsageCount) {
    SourceRecord first = group.get(0);
    StringBuilder contentBuilder = new StringBuilder();
    // 使用 LinkedHashMap 保持首次出现顺序
    Map<String, SourceToolCall> toolCallsById = new LinkedHashMap<>();

    for (SourceRecord record : group) {
      if (!record.content().isEmpty()) {
        if (!contentBuilder.isEmpty()) {
          contentBuilder.append("\n");
        }
        contentBuilder.append(record.content());
      }
      for (SourceToolCall tc : record.toolCalls()) {
        SourceToolCall existing = toolCallsById.get(tc.toolCallId());
        if (existing == null) {
          toolCallsById.put(tc.toolCallId(), tc);
        } else {
          // 流式声明可能先给出空对象，后续完整参数不能被该占位值挡住。
          if ((existing.input().isBlank() || "{}".equals(existing.input()))
              && !tc.input().isBlank()) {
            toolCallsById.put(tc.toolCallId(), tc);
          }
        }
      }
    }

    // Usage: 分量最大值
    SourceRecordUsage mergedUsage = mergeUsage(group);

    // 确定最后一片的 stop_reason（如果有）
    Optional<String> lastStopReason = Optional.empty();
    for (int i = group.size() - 1; i >= 0; i--) {
      lastStopReason = group.get(i).responseStopReason();
      if (lastStopReason.isPresent()) {
        break;
      }
    }

    // 分配唯一 turnId 和 callId
    String baseId = first.responseMessageId().orElse("");
    int count = identityUsageCount.merge(baseId, 1, Integer::sum);
    String uniqueId = ID_PREFIX + baseId + "$" + count;

    return new SourceRecord(
        first.locator(),
        first.eventIndex(),
        "assistant",
        Optional.of(uniqueId),
        first.model(),
        first.timestamp(),
        Optional.of(uniqueId),
        mergedUsage,
        List.copyOf(toolCallsById.values()),
        first.toolUseId(),
        first.toolName(),
        first.toolError(),
        first.relation() != null ? first.relation() : SourceRecordRelation.empty(),
        contentBuilder.toString(),
        first.responseMessageId(),
        lastStopReason);
  }

  private static SourceRecordUsage mergeUsage(List<SourceRecord> group) {
    long maxInput = 0;
    long maxCacheRead = 0;
    long maxCacheWrite = 0;
    long maxOutput = 0;
    for (SourceRecord record : group) {
      SourceRecordUsage usage = record.usage();
      maxInput = Math.max(maxInput, usage.inputTokens());
      maxCacheRead = Math.max(maxCacheRead, usage.cacheReadInputTokens());
      maxCacheWrite = Math.max(maxCacheWrite, usage.cacheCreationInputTokens());
      maxOutput = Math.max(maxOutput, usage.outputTokens());
    }
    return new SourceRecordUsage(maxInput, maxCacheRead, maxCacheWrite, maxOutput);
  }
}
