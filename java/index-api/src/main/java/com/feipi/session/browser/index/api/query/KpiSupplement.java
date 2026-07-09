package com.feipi.session.browser.index.api.query;

/** dashboard 补充 KPI 聚合行。 */
public interface KpiSupplement {
  long activeProjects24h();

  long activeProjects7d();

  long newProjects7d();

  long activeProjectsPrevious7d();

  long todaySessions();

  double avgDailySessions7d();

  double medianDurationSeconds();

  long eligibleSessions();

  Double p50CacheRatio();

  long lowReadSessions();

  long affectedFailureSessions();

  long repeatedFailureSessions();
}
