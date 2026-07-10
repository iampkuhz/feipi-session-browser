package com.feipi.session.browser.web.model;

import com.feipi.session.browser.index.api.query.SessionRecord;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Session token 趋势 bucket 构造器。 */
public final class TokenTrendBuckets {

  private TokenTrendBuckets() {}

  /** 按指定粒度聚合 session token 趋势点。 */
  public static List<Point> fromSessions(List<SessionRecord> sessions, String grain) {
    Map<String, long[]> buckets = new LinkedHashMap<>();
    for (SessionRecord session : sessions) {
      LocalDate date = WebDisplayValues.parseDate(session.startedAt());
      if (date == null) {
        continue;
      }
      String key = WebDisplayValues.bucketLabel(date, grain);
      long[] values = buckets.computeIfAbsent(key, ignored -> new long[5]);
      values[0] += session.freshInputTokens();
      values[1] += session.cacheReadTokens();
      values[2] += session.cacheWriteTokens();
      values[3] += session.outputTokens();
      values[4] += session.totalTokens();
    }

    List<Point> points = new ArrayList<>();
    for (Map.Entry<String, long[]> entry : buckets.entrySet()) {
      long[] values = entry.getValue();
      points.add(new Point(entry.getKey(), values[0], values[1], values[2], values[3], values[4]));
    }
    return List.copyOf(points);
  }

  /**
   * Token 趋势点。
   *
   * @param label bucket 标签
   * @param fresh 新输入 token 数
   * @param cacheRead 缓存读取 token 数
   * @param cacheWrite 缓存写入 token 数
   * @param output 输出 token 数
   * @param total 总 token 数
   */
  public record Point(
      /* 分组展示标签 */
      String label,
      /* 新输入令牌数量 */
      long fresh,
      /* 缓存读取令牌数量 */
      long cacheRead,
      /* 缓存写入令牌数量 */
      long cacheWrite,
      /* 输出令牌数量 */
      long output,
      /* 令牌总数量 */
      long total) {}
}
