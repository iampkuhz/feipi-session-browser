package com.feipi.session.browser.web.api;

import com.feipi.session.browser.index.api.query.SessionListSummary;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsSummaryResponse;
import java.util.Map;

/** Session summary API 响应构造器。 */
final class ApiSessionSummaries {

  private ApiSessionSummaries() {}

  /** 构建 Session summary API 响应。 */
  static SessionsSummaryResponse response(
      Map<String, String> params, SessionListSummary summary, PageStateDto state) {
    return new SessionsSummaryResponse(
        ApiResponses.SCHEMA_VERSION,
        ApiQueryParams.sessionsFilterEcho(params),
        summary.sessionCount(),
        summary.projectCount(),
        TokenSegments.of(
            summary.freshInputTokens(),
            summary.cacheReadTokens(),
            summary.cacheWriteTokens(),
            summary.outputTokens()),
        summary.failedToolCount(),
        state);
  }
}
