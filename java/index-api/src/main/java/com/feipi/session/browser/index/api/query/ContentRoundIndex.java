package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import java.io.IOException;
import java.util.Map;
import java.util.Objects;
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
