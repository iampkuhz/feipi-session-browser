package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import java.io.IOException;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;

/** 保存会话全局调用到轮次的紧凑索引，不保留调用正文。 */
public final class ContentRoundIndex {
  private final Map<String, Integer> calls;
  private final int count;

  private ContentRoundIndex(Map<String, Integer> calls, int count) {
    this.calls = calls;
    this.count = count;
  }

  /** 通过重放有界内容单元构建全局逻辑轮次。 */
  public static ContentRoundIndex build(NormalizedSessionContent content, long observedUserMessages)
      throws IOException {
    Objects.requireNonNull(content, "content");
    var grouping = new RoundGrouping(content.header().agent());
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) grouping.add(call);
      }
    }
    int count = grouping.count();
    return new ContentRoundIndex(
        grouping.calls(), count == 0 && observedUserMessages > 0 ? 1 : count);
  }

  /**
   * 返回 Codex 的轮次证据类型；空值表示未确认独立请求边界。
   *
   * @param agent 会话来源
   * @param call 归一化调用
   * @return 响应用量记录、累计计量边界或空字符串
   */
  public static String modelCallEvidence(NormalizedAgent agent, NormalizedCall call) {
    return RoundGrouping.evidence(agent, call);
  }

  /**
   * 读取明确绑定到 Side Chat 源任务的调用事实。
   *
   * @param call 已归一化的调用
   * @return 源任务身份和可选计时，未证实时为空
   */
  public static Optional<SideTask> sideTask(NormalizedCall call) {
    if (call.scope() != CallScope.MAIN) return Optional.empty();
    String identity = "", start = "";
    Long duration = null;
    for (var unit : call.sourceUnits()) {
      String value = Objects.toString(unit.get("text"), "");
      switch (Objects.toString(unit.get("type"), "")) {
        case "codex_context_side_task_id" -> identity = value;
        case "codex_context_side_task_started_at" -> start = value;
        case "codex_context_side_task_duration_ms" -> duration = nonNegativeMillis(value);
        default -> {}
      }
    }
    return identity.isBlank() || call.turnId().filter(identity::equals).isEmpty()
        ? Optional.empty()
        : Optional.of(new SideTask(identity, start, duration));
  }

  private static Long nonNegativeMillis(String value) {
    try {
      long duration = Long.parseLong(value);
      return duration >= 0 ? duration : null;
    } catch (NumberFormatException invalid) {
      return null;
    }
  }

  /**
   * 源任务计时不代表个别模型调用耗时。
   *
   * @param identity 源显式任务标识
   * @param startedAt 源报告的开始时间，无证据时为空字符串
   * @param durationMs 源报告或完整边界导出的任务耗时，无证据时为空
   */
  public record SideTask(String identity, String startedAt, Long durationMs) {}

  /** 返回逻辑轮次总数，并兼容仅观测到用户消息的会话。 */
  public int roundCount() {
    return count;
  }

  /** 返回从一开始的轮次序号；调用不存在时返回空值。 */
  public OptionalInt roundIndexForCall(String callId) {
    Integer index = calls.get(callId);
    return index == null ? OptionalInt.empty() : OptionalInt.of(index);
  }
}
