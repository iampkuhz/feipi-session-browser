package com.feipi.session.browser.web.model;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 项目 token 趋势按开始时刻的 UTC 日期聚合，不采用展示时区或结束日。 */
@DisplayName("TokenTrendBuckets UTC started-at cohort")
class TokenTrendBucketsTest {

  @Test
  @DisplayName("UTC 午夜及 offset 跨日不采用上海展示日期")
  void groupsUtcDaysAcrossMidnightAndOffset() {
    var points = TokenTrendBuckets.fromSessions(monthBoundarySessions(), "day");
    assertThat(points)
        .extracting(TokenTrendBuckets.Point::label)
        .containsExactly("2026-01-31", "2026-02-01");
    assertThat(points).extracting(TokenTrendBuckets.Point::total).containsExactly(20L, 10L);
    assertThat(points.getFirst().provenance().unknownSessionCount()).isEqualTo(2);
    assertThat(points.getFirst().provenance().freshInput()).isEqualTo("unknown");
  }

  @Test
  @DisplayName("跨月按 UTC 开始日期归桶并保留整段用量")
  void groupsUtcMonths() {
    var points = TokenTrendBuckets.fromSessions(monthBoundarySessions(), "month");
    assertThat(points)
        .extracting(TokenTrendBuckets.Point::label)
        .containsExactly("2026-01", "2026-02");
    assertThat(points).extracting(TokenTrendBuckets.Point::total).containsExactly(20L, 10L);
  }

  @Test
  @DisplayName("ISO 跨年周以 UTC 周一归桶")
  void groupsIsoWeeksAcrossYear() {
    var points =
        TokenTrendBuckets.fromSessions(
            List.of(
                session("2020-12-27T23:30:00Z"),
                session("2020-12-28T00:30:00Z"),
                session("2021-01-03T23:30:00Z")),
            "week");
    assertThat(points)
        .extracting(TokenTrendBuckets.Point::label)
        .containsExactly("2020-12-21", "2020-12-28");
    assertThat(points).extracting(TokenTrendBuckets.Point::total).containsExactly(10L, 20L);
  }

  @Test
  @DisplayName("未知或非法开始日期不回退到结束日或今天")
  void excludesUnknownStartedDates() {
    assertThat(
            TokenTrendBuckets.fromSessions(
                List.of(session(null), session(""), session("not-a-date")), "day"))
        .isEmpty();
  }

  /** 返回 UTC 月末和 offset 跨日的纯合成会话。 */
  private static List<SessionRecord> monthBoundarySessions() {
    return List.of(
        session("2026-01-31T23:30:00Z"),
        session("2026-02-01T00:15:00+02:00"),
        session("2026-02-01T00:30:00Z"));
  }

  /**
   * 构造整段 10 tokens 的合成会话，旧构造器明确保留 unknown 来源。
   *
   * @param startedAt 待验证的开始时间
   * @return 与真实数据无关的查询行
   */
  private static SessionRecord session(String startedAt) {
    return new SessionRow(
        "synthetic:cohort",
        "synthetic",
        "cohort",
        "",
        "",
        "",
        "",
        startedAt,
        "2028-01-01T00:00:00Z",
        0,
        0,
        0,
        "",
        "",
        "fixture",
        1,
        1,
        0,
        1,
        6,
        2,
        1,
        10,
        0,
        0,
        0,
        0,
        "");
  }
}
