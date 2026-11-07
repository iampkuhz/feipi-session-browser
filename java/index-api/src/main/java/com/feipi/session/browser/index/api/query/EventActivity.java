package com.feipi.session.browser.index.api.query;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 按源事件 UTC 日期归集的观察子集，与会话开始日累计量独立。
 *
 * <p>覆盖与未日期化分量描述整个所选来源集合，不能按未知日期分配到查询窗口。日桶只覆盖查询窗口；不存在的日桶不表示实测零。token 仅为现代 Codex usage
 * 的报告日，不能解释为完整账单或实际消耗发生日。
 *
 * @param days 查询窗口中的实际观察日桶
 * @param coverage 所选索引会话集合的覆盖计数，不代表完整源历史
 * @param undatedTokens 有分量证据但无法日期化的现代 usage
 */
public record EventActivity(
    List<Day> days, Map<String, Long> coverage, Map<String, TokenComponent> undatedTokens) {

  /** 保存不可变的查询结果，拒绝负覆盖计数。 */
  public EventActivity {
    days = List.copyOf(days);
    coverage = Map.copyOf(coverage);
    undatedTokens = components(undatedTokens);
    if (coverage.values().stream().anyMatch(value -> value < 0)) {
      throw new IllegalArgumentException("event activity coverage must be nonnegative");
    }
  }

  private static Map<String, TokenComponent> components(Map<String, TokenComponent> values) {
    Map<String, TokenComponent> copy = Map.copyOf(values);
    if (!copy.keySet().equals(Set.of("fresh", "cacheRead", "cacheWrite", "output"))) {
      throw new IllegalArgumentException("event activity requires four token components");
    }
    return copy;
  }

  /**
   * 一个有实际源事件的 UTC 日桶，消息数只是观察下界而不是完整真人提问量。
   *
   * @param date 源事件对应的 ISO UTC 日期
   * @param observedUserMessages 显式主 user 消息数，已排除工具、上下文和子会话
   * @param tokens 四个现代 usage 分量及各自覆盖
   */
  public record Day(String date, long observedUserMessages, Map<String, TokenComponent> tokens) {

    /** 验证日期、观察计数和四个不可变分量。 */
    public Day {
      java.time.LocalDate.parse(date);
      if (observedUserMessages < 0) {
        throw new IllegalArgumentException("observed user messages must be nonnegative");
      }
      tokens = components(tokens);
    }
  }

  /**
   * 一个 token 分量的已上报金额与来源覆盖；未测量金额保持 null。
   *
   * @param reportedTokens provider 实测金额；没有实测样本时必须为 null
   * @param reportedSamples provider 实测样本数，包含实测零
   * @param estimatedSamples 仅有估算证据的样本数，不计入实测金额
   * @param unavailableSamples 明确无法得到该分量的样本数
   * @param unknownSamples 没有足够来源证据的样本数
   * @param mixedSamples 来源混合、不能声称全部实测的样本数
   */
  public record TokenComponent(
      Long reportedTokens,
      long reportedSamples,
      long estimatedSamples,
      long unavailableSamples,
      long unknownSamples,
      long mixedSamples) {

    /** 保留实测零与未知金额的区别，拒绝不一致或负计数。 */
    public TokenComponent {
      if (reportedSamples < 0
          || estimatedSamples < 0
          || unavailableSamples < 0
          || unknownSamples < 0
          || mixedSamples < 0) {
        throw new IllegalArgumentException("event token sample counts must be nonnegative");
      }
      if ((reportedTokens == null) != (reportedSamples == 0)
          || (reportedTokens != null && reportedTokens < 0)) {
        throw new IllegalArgumentException("event token amount requires reported samples");
      }
    }
  }
}
