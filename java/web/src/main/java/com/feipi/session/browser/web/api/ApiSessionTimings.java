package com.feipi.session.browser.web.api;

/** 不将缺少来源的旧执行数字作为可用 API 计时。 */
final class ApiSessionTimings {
  private ApiSessionTimings() {}

  static Double available(Double seconds, String precision) {
    return "measured".equals(precision) || "partial".equals(precision) ? seconds : null;
  }
}
