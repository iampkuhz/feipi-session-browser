package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Optional;

/**
 * 源记录之间的父子关系。
 *
 * <p>用于把 Codex child rollout、Claude sidecar 等稳定可见的父子证据传递给归一化层。该类型只承载显式证据，不从隐藏 runtime 状态推断。
 *
 * @param subagentId 子 agent 线程或实例标识
 * @param parentThreadId 父线程标识
 * @param parentToolCallId 触发子线程的父工具调用标识
 * @param parentCallId 触发子线程的父 LLM call 标识，缺失时由归一化层补齐
 * @param parentToolName 触发子线程的父工具名
 */
@DomainModel
public record SourceRecordRelation(
    Optional<String> subagentId,
    Optional<String> parentThreadId,
    Optional<String> parentToolCallId,
    Optional<String> parentCallId,
    Optional<String> parentToolName) {

  /** 规范化 Optional 字段。 */
  public SourceRecordRelation {
    subagentId = subagentId == null ? Optional.empty() : subagentId;
    parentThreadId = parentThreadId == null ? Optional.empty() : parentThreadId;
    parentToolCallId = parentToolCallId == null ? Optional.empty() : parentToolCallId;
    parentCallId = parentCallId == null ? Optional.empty() : parentCallId;
    parentToolName = parentToolName == null ? Optional.empty() : parentToolName;
  }

  /**
   * 空关系。
   *
   * @return 无父子证据的关系对象
   */
  public static SourceRecordRelation empty() {
    return new SourceRecordRelation(
        Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty());
  }

  /**
   * 是否包含 subagent 证据。
   *
   * @return 有子 agent 标识时返回 true
   */
  public boolean hasSubagentEvidence() {
    return subagentId.isPresent();
  }
}
