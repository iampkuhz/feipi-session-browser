package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import org.junit.jupiter.api.Test;

/** 验证显式分页请求的参数边界；即使兼容会话为空，也不得绕过校验。 */
class SessionContentPaginationTest {
  @Test
  void rejectsInvalidLimitsAndMalformedCursorsInsteadOfReturningSuccess() {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var handler =
        new SessionDetailApiHandler(
            ctx ->
                new SessionDetailApiHandler.LoadedDetail(
                    new SessionDetailApiResponses.SessionDetailFilterEcho(
                        "codex", "health", "standard", "", ""),
                    new SessionDetailUseCase.AnnotatedDetailContext(
                        detail,
                        SessionAnomalySummary.empty(detail.sessionRow().sessionKey()),
                        null),
                    "/synthetic",
                    false));
    JavalinTest.test(
        Javalin.create(
            config -> {
              config.routes.get("/rounds", handler::handleRounds);
              config.routes.get("/payloads", handler::handlePayloads);
              config.routes.get("/execution", handler::handleExecution);
            }),
        (app, client) -> {
          for (String route : new String[] {"/rounds", "/payloads", "/execution"}) {
            for (String query :
                new String[] {"?limit=0", "?limit=501", "?limit=no", "?cursor=broken"}) {
              var response = client.get(route + query);
              assertThat(response.code()).as(route + query).isEqualTo(400);
            }
          }
        });
  }
}
