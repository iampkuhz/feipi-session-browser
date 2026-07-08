package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 会话详情装配器。
 *
 * <p>将 {@link SessionRow} 和 {@link NormalizedSessionArtifact} 组合为 {@link SessionDetail}。 装配逻辑包括：
 *
 * <ul>
 *   <li>将归一化调用按轮次分组（主会话调用顺序分配，子 agent 调用关联到父调用轮次）。
 *   <li>从调用和工具执行生成 payload 来源列表。
 *   <li>构建包含制品 hash 和 index 版本的缓存键。
 * </ul>
 *
 * <p>校验放置：本类信任已验证的 {@link SessionRow} 和 {@link NormalizedSessionArtifact}， 不重复 domain 层校验。
 */
public final class SessionDetailAssembler {

  /** 防止外部实例化。 */
  private SessionDetailAssembler() {}

  /**
   * 将会话行和归一化制品装配为详情模型。
   *
   * @param sessionRow 数据库会话行
   * @param artifact 归一化制品，不得为 null
   * @param visibility payload 可见性策略
   * @param artifactPath 制品路径
   * @param indexVersion index schema 版本号
   * @return 装配完成的会话详情
   */
  public static SessionDetail assemble(
      SessionRow sessionRow,
      NormalizedSessionArtifact artifact,
      PayloadVisibility visibility,
      String artifactPath,
      int indexVersion) {
    Objects.requireNonNull(sessionRow, "sessionRow 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    List<CallRound> rounds = buildRounds(artifact.calls(), artifact.toolExecutions());
    if (rounds.isEmpty() && sessionRow.userMessageCount() > 0) {
      rounds = List.of(new CallRound(1, List.of(), List.of(), null));
    }
    List<PayloadSource> payloadSources = buildPayloadSources(artifact.calls(), visibility);
    String cacheKey = buildCacheKey(artifactPath, indexVersion);

    return new SessionDetail(
        sessionRow,
        rounds,
        payloadSources,
        visibility,
        artifactPath,
        artifact.schemaVersion(),
        cacheKey);
  }

  /**
   * 将调用列表按轮次分组。
   *
   * <p>主会话调用按顺序分配到独立轮次，子 agent 调用合并到其父调用所在的轮次。 没有父调用的子 agent 调用创建独立轮次。
   *
   * @param calls 归一化调用列表，按遍历顺序排列
   * @return 轮次列表
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

    // callId → 所在轮次索引的映射
    Map<String, Integer> callToRoundIndex = new LinkedHashMap<>();
    Map<String, Integer> turnToRoundIndex = new LinkedHashMap<>();
    List<List<String>> roundCallIds = new ArrayList<>();
    List<List<String>> roundToolCallIds = new ArrayList<>();
    List<String> roundParentCallIds = new ArrayList<>();
    List<long[]> roundUsage = new ArrayList<>();

    for (NormalizedCall call : calls) {
      if (call.scope() == CallScope.MAIN) {
        String turnKey = call.turnId().orElse("");
        Integer existingRoundIdx = turnKey.isEmpty() ? null : turnToRoundIndex.get(turnKey);
        if (existingRoundIdx != null) {
          roundCallIds.get(existingRoundIdx).add(call.callId());
          addUnique(roundToolCallIds.get(existingRoundIdx), toolIds(call));
          addUsage(roundUsage.get(existingRoundIdx), call);
          callToRoundIndex.put(call.callId(), existingRoundIdx);
        } else {
          // 主会话逻辑 turn 创建新轮次；同一个 provider turn 内的多条 request/response 记录合并展示。
          int roundIdx = roundCallIds.size();
          List<String> callIds = new ArrayList<>();
          callIds.add(call.callId());
          roundCallIds.add(callIds);
          roundToolCallIds.add(new ArrayList<>(toolIds(call)));
          roundParentCallIds.add("");
          roundUsage.add(usageValues(call));
          callToRoundIndex.put(call.callId(), roundIdx);
          if (!turnKey.isEmpty()) {
            turnToRoundIndex.put(turnKey, roundIdx);
          }
        }
      } else {
        // 子 agent 调用合并到父调用所在轮次
        String parentCallId = call.parentCallId().orElse("");
        Integer parentRoundIdx = callToRoundIndex.get(parentCallId);
        if (parentRoundIdx != null) {
          roundCallIds.get(parentRoundIdx).add(call.callId());
          addUnique(roundToolCallIds.get(parentRoundIdx), toolIds(call));
          addUsage(roundUsage.get(parentRoundIdx), call);
          callToRoundIndex.put(call.callId(), parentRoundIdx);
        } else {
          // 无父调用映射，创建独立轮次
          int roundIdx = roundCallIds.size();
          List<String> callIds = new ArrayList<>();
          callIds.add(call.callId());
          roundCallIds.add(callIds);
          roundToolCallIds.add(new ArrayList<>(toolIds(call)));
          roundParentCallIds.add(parentCallId);
          roundUsage.add(usageValues(call));
          callToRoundIndex.put(call.callId(), roundIdx);
        }
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
    List<String> result = new ArrayList<>();
    result.addAll(call.response().toolCallIds());
    for (String toolResultId : call.request().toolResultIds()) {
      if (!result.contains(toolResultId)) {
        result.add(toolResultId);
      }
    }
    return result;
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

  /**
   * 从调用列表生成 payload 来源。
   *
   * <p>为每个调用生成请求和响应 payload 来源。归一化调用始终代表一次 LLM 交互， 具有请求和响应两侧内容。 标准可见性下标记为截断，完整可见性下不截断。
   *
   * <p>内容解析通过 source unit 引用完成，本层只负责生成标识符和可见性标记。
   *
   * @param calls 归一化调用列表
   * @param visibility payload 可见性
   * @return payload 来源列表
   */
  static List<PayloadSource> buildPayloadSources(
      List<NormalizedCall> calls, PayloadVisibility visibility) {
    boolean truncated = visibility == PayloadVisibility.STANDARD;
    List<PayloadSource> sources = new ArrayList<>();

    for (NormalizedCall call : calls) {
      boolean isSubagent = call.scope() == CallScope.SUBAGENT;
      String prefix = isSubagent ? "sa" : "main";

      // 每次调用都有请求和响应两侧
      PayloadSourceKind requestKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST;
      sources.add(
          new PayloadSource(
              prefix + ":req:" + call.callId(),
              requestKind,
              call.callId(),
              "Request " + call.callKey(),
              truncated));

      PayloadSourceKind responseKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
      sources.add(
          new PayloadSource(
              prefix + ":resp:" + call.callId(),
              responseKind,
              call.callId(),
              "Response " + call.callKey(),
              truncated));
    }
    return sources;
  }

  /**
   * 构建缓存键，包含制品路径和 index 版本号。
   *
   * <p>缓存键用于 session data cache，保证制品更新或 index schema 变化时缓存失效。
   *
   * @param artifactPath 制品路径
   * @param indexVersion index schema 版本
   * @return 格式为 {@code artifact:<path>:v<version>} 的缓存键
   */
  public static String buildCacheKey(String artifactPath, int indexVersion) {
    if (artifactPath == null || artifactPath.isEmpty()) {
      return "novalue:v" + indexVersion;
    }
    return "artifact:" + artifactPath + ":v" + indexVersion;
  }
}
