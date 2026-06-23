package com.feipi.session.browser.query.api;

import java.util.List;
import java.util.Objects;

/**
 * 会话对话轮次。
 *
 * <p>将归一化调用按逻辑轮次分组。主会话调用按顺序分配到轮次， 子 agent 调用通过 {@code parentCallId} 关联到触发它的父调用。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code roundIndex} 必须 >= 1。
 *   <li>{@code calls} 不得为 null，使用不可变列表。
 *   <li>{@code toolCallIds} 不得为 null，使用不可变列表。
 * </ul>
 *
 * @param roundIndex 从 1 开始的轮次序号
 * @param calls 本轮次包含的归一化调用 callId 列表
 * @param toolCallIds 本轮次关联的工具调用 ID 列表
 * @param parentCallId 触发本轮次的父调用 ID，首轮次为空
 */
public record CallRound(
    int roundIndex, List<String> calls, List<String> toolCallIds, String parentCallId) {

  /**
   * 紧凑构造器，验证轮次不变量。
   *
   * @throws IllegalArgumentException 当 roundIndex 小于 1 时
   * @throws NullPointerException 当集合字段为 null 时
   */
  public CallRound {
    if (roundIndex < 1) {
      throw new IllegalArgumentException("roundIndex 必须 >= 1; got " + roundIndex);
    }
    Objects.requireNonNull(calls, "calls 不得为 null");
    Objects.requireNonNull(toolCallIds, "toolCallIds 不得为 null");
    calls = List.copyOf(calls);
    toolCallIds = List.copyOf(toolCallIds);
    parentCallId = parentCallId == null ? "" : parentCallId;
  }

  /**
   * 创建不含父调用的轮次。
   *
   * @param roundIndex 轮次序号
   * @param calls 调用 ID 列表
   * @param toolCallIds 工具调用 ID 列表
   * @return 新轮次实例
   */
  public static CallRound of(int roundIndex, List<String> calls, List<String> toolCallIds) {
    return new CallRound(roundIndex, calls, toolCallIds, null);
  }

  /** 本轮次的调用数量。 */
  public int callCount() {
    return calls.size();
  }

  /** 本轮次的工具调用数量。 */
  public int toolCallCount() {
    return toolCallIds.size();
  }

  /** 是否为空轮次（无调用且无工具调用）。 */
  public boolean isEmpty() {
    return calls.isEmpty() && toolCallIds.isEmpty();
  }
}
