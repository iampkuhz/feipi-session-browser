package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.query.api.CallRound;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/** 扫描持久化和详情展示共享的逻辑轮次分组。 */
public final class RoundAssembler {
  private RoundAssembler() {}

  /**
   * 包括仅用户内容的单轮兼容逻辑，供扫描与详情使用同一口径。
   *
   * @param artifact 已归一化的会话制品
   * @param userMessages 已观测的用户消息数
   * @return 逻辑轮次列表
   */
  public static List<CallRound> buildRounds(NormalizedSessionArtifact artifact, long userMessages) {
    List<CallRound> rounds = buildRounds(artifact.calls(), artifact.toolExecutions());
    return rounds.isEmpty() && userMessages > 0
        ? List.of(new CallRound(1, List.of(), List.of(), null))
        : rounds;
  }

  /**
   * 使用无工具执行信息的调用列表构建轮次。
   *
   * @param calls 按遍历顺序排列的调用
   * @return 逻辑轮次列表
   */
  public static List<CallRound> buildRounds(List<NormalizedCall> calls) {
    return buildRounds(calls, List.of());
  }

  /**
   * 将调用列表按轮次分组，并把失败工具执行聚合到对应轮次。
   *
   * @param calls 归一化调用列表，按遍历顺序排列
   * @param toolExecutions 归一化工具执行列表，按遍历顺序排列
   * @return 轮次列表
   */
  public static List<CallRound> buildRounds(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {
    Objects.requireNonNull(calls, "calls 不得为 null");
    Objects.requireNonNull(toolExecutions, "toolExecutions 不得为 null");
    if (calls.isEmpty()) {
      return List.of();
    }

    RoundGrouping grouping = new RoundGrouping();
    List<List<String>> roundCallIds = new ArrayList<>();
    List<List<String>> roundToolCallIds = new ArrayList<>();
    List<String> roundParentCallIds = new ArrayList<>();
    List<long[]> roundUsage = new ArrayList<>();

    for (NormalizedCall call : calls) {
      int roundIdx = grouping.add(call) - 1;
      if (roundIdx == roundCallIds.size()) {
        roundCallIds.add(new ArrayList<>(List.of(call.callId())));
        roundToolCallIds.add(new ArrayList<>(toolIds(call)));
        roundParentCallIds.add(
            call.scope() == CallScope.MAIN ? "" : call.parentCallId().orElse(""));
        roundUsage.add(usageValues(call));
      } else {
        roundCallIds.get(roundIdx).add(call.callId());
        addUnique(roundToolCallIds.get(roundIdx), toolIds(call));
        addUsage(roundUsage.get(roundIdx), call);
      }
    }

    // 分配工具调用到对应轮次
    // 工具调用的 declaredByCallId 决定它属于哪个轮次
    // 这里只记录 callId 级别的关联，实际工具执行由外层 assembler 处理

    List<CallRound> result = new ArrayList<>();
    for (int i = 0; i < roundCallIds.size(); i++) {
      long[] usage = roundUsage.get(i);
      result.add(
          new CallRound(
              i + 1,
              List.copyOf(roundCallIds.get(i)),
              List.copyOf(roundToolCallIds.get(i)),
              roundParentCallIds.get(i).isEmpty() ? null : roundParentCallIds.get(i),
              usage[0],
              usage[1],
              usage[2],
              usage[3],
              usage[4],
              failedToolCallIds(roundCallIds.get(i), toolExecutions)));
    }
    return result;
  }

  private static List<String> failedToolCallIds(
      List<String> roundCalls, List<NormalizedToolExecution> toolExecutions) {
    List<String> result = new ArrayList<>();
    for (NormalizedToolExecution execution : toolExecutions) {
      if (roundCalls.contains(execution.declaredByCallId()) && hasFailedStatus(execution)) {
        result.add(execution.toolCallId());
      }
    }
    return result;
  }

  private static boolean hasFailedStatus(NormalizedToolExecution execution) {
    return execution.status().map(status -> !status.isBlank()).orElse(false);
  }

  private static List<String> toolIds(NormalizedCall call) {
    return call.response().toolCallIds();
  }

  private static void addUnique(List<String> target, List<String> values) {
    for (String value : values) {
      if (!target.contains(value)) {
        target.add(value);
      }
    }
  }

  private static long[] usageValues(NormalizedCall call) {
    return new long[] {
      call.usage().fresh(),
      call.usage().cacheRead(),
      call.usage().cacheWrite(),
      call.usage().output(),
      call.usage().total()
    };
  }

  private static void addUsage(long[] target, NormalizedCall call) {
    target[0] += call.usage().fresh();
    target[1] += call.usage().cacheRead();
    target[2] += call.usage().cacheWrite();
    target[3] += call.usage().output();
    target[4] += call.usage().total();
  }
}
