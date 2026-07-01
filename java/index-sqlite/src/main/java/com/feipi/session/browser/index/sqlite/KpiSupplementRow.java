package com.feipi.session.browser.index.sqlite;

/**
 * Dashboard KPI 补充数据行。
 *
 * <p>包含 6 张 KPI card 所需的补充聚合指标，支持 agent scope 过滤。 这些数据无法从 {@link DashboardRow} 直接获得，需要额外的时间窗口或分位数查询。
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
 * @param lowReadSessions eligible sessions 中 cache read ratio < 20% 的 session 数
 * @param affectedFailureSessions failed_tool_count > 0 的 session 数
 * @param repeatedFailureSessions failed_tool_count > 1 的 session 数
 */
public record KpiSupplementRow(
    long activeProjects24h,
    long activeProjects7d,
    long newProjects7d,
    long activeProjectsPrevious7d,
    long todaySessions,
    double avgDailySessions7d,
    double medianDurationSeconds,
    long eligibleSessions,
    Double p50CacheRatio,
    long lowReadSessions,
    long affectedFailureSessions,
    long repeatedFailureSessions) {}
