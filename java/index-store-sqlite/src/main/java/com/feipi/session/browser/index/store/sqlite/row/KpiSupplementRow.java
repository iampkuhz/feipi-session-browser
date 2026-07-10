package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.KpiSupplement;
import com.feipi.session.browser.validation.Finite;
import com.feipi.session.browser.validation.Ratio;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * Dashboard KPI 补充数据行。
 *
 * <p>包含 6 张 KPI card 所需的补充聚合指标，支持 agent scope 过滤。 这些数据无法从 {@link DashboardRow}
 * 直接获得，需要额外的时间窗口或分位数查询。
 *
 * @param activeProjects24h 最近 24 小时内有 session 的 project 去重数
 * @param activeProjects7d 最近 7 天内有 session 的 project 去重数
 * @param newProjects7d first seen 落在最近 7 天内的 project 去重数
 * @param activeProjectsPrevious7d 上个 7 天（8-14 天前）有 session 的 project 去重数，用于 badge 计算
 * @param todaySessions 今日开始的 session 数
 * @param avgDailySessions7d 最近 7 天每日 session 数的算术平均值
 * @param medianDurationSeconds session duration 的中位数（秒）
 * @param eligibleSessions input-side tokens > 0 的 session 数
 * @param p50CacheRatio eligible sessions 的 per-session cache read ratio 中位数，null 表示不可计算
 * @param lowReadSessions eligible sessions 中 cache read ratio {@code < 20%} 的 session 数
 * @param affectedFailureSessions {@code failed_tool_count > 0} 的 session 数
 * @param repeatedFailureSessions {@code failed_tool_count > 1} 的 session 数
 */
public record KpiSupplementRow(
    /* 最近 24 小时内有 session 的 project 去重数。 */ @PositiveOrZero long activeProjects24h,
    /* 最近 7 天内有 session 的 project 去重数。 */ @PositiveOrZero long activeProjects7d,
    /* first seen 落在最近 7 天内的 project 去重数。 */ @PositiveOrZero long newProjects7d,
    /* 上个 7 天（8-14 天前）有 session 的 project 去重数，用于 badge 计算。 */ @PositiveOrZero
        long activeProjectsPrevious7d,
    /* 今日开始的 session 数。 */ @PositiveOrZero long todaySessions,
    /* 最近 7 天每日 session 数的算术平均值。 */ @Finite @PositiveOrZero double avgDailySessions7d,
    /* session duration 的中位数（秒）。 */ @Finite @PositiveOrZero double medianDurationSeconds,
    /* 输入侧令牌大于零的会话数量。 */ @PositiveOrZero long eligibleSessions,
    /* eligible sessions 的 per-session cache read ratio 中位数，null 表示不可计算。 */ @Ratio
        Double p50CacheRatio,
    /* 符合条件会话中缓存读取比例低于二成的会话数量。 */ @PositiveOrZero long lowReadSessions,
    /* 失败工具数大于零的会话数量。 */ @PositiveOrZero long affectedFailureSessions,
    /* 失败工具数大于一的会话数量。 */ @PositiveOrZero long repeatedFailureSessions)
    implements KpiSupplement {

  /** 紧凑构造器，校验 record component 约束。 */
  public KpiSupplementRow {
    ValidationSupport.validateCanonicalConstructor(
        KpiSupplementRow.class,
        activeProjects24h,
        activeProjects7d,
        newProjects7d,
        activeProjectsPrevious7d,
        todaySessions,
        avgDailySessions7d,
        medianDurationSeconds,
        eligibleSessions,
        p50CacheRatio,
        lowReadSessions,
        affectedFailureSessions,
        repeatedFailureSessions);
  }
}
