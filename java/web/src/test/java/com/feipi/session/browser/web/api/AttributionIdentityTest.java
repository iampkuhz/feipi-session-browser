package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 验证分页或子代理局部序号重新从一开始时，归因仍准确绑定稳定调用身份。 */
class AttributionIdentityTest {
  @Test
  void largeContentTailAndChildAcrossRoundsUseExactCallId() throws Exception {
    verifyIdentity(10234, false);
  }

  @Test
  void legacyArtifactAlsoValidatesCallIdOwnership() throws Exception {
    verifyIdentity(4, true);
  }

  private static void verifyIdentity(int mainCalls, boolean legacy) throws Exception {
    var calls = new ArrayList<NormalizedCall>();
    for (int i = 1; i <= mainCalls; i++) calls.add(call(i, false, i <= mainCalls / 2 ? 1 : 2, 0));
    calls.add(call(mainCalls + 1, true, 1, 1));
    calls.add(call(mainCalls + 2, true, 2, mainCalls));
    var content =
        NormalizedSessionContent.fromLists(
            new NormalizedContentHeader(
                NormalizedConstants.SCHEMA_VERSION,
                NormalizedAgent.CODEX,
                new NormalizedSessionMetadata(Map.of()),
                Map.of(
                    "calls",
                    (long) calls.size(),
                    "toolExecutions",
                    0L,
                    "diagnostics",
                    0L,
                    "sourceFiles",
                    0L,
                    "sourceUnitCatalog",
                    0L,
                    "sourceUnitSequenceEntries",
                    0L)),
            List.of(),
            calls,
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var artifact = legacy ? content.toArtifact() : null;
    var service =
        new SessionApiService(
            (key, visibility) ->
                Optional.of(new SessionDetailUseCase.DetailContext(detail, artifact, content)));
    var handler = new SessionApiHandler(service);
    JavalinTest.test(
        Javalin.create(
            config -> {
              config.routes.get(
                  "/round/1",
                  ctx -> handler.handleAttribution(ctx, "codex", "health", 1, 1, "response"));
              config.routes.get(
                  "/round/2",
                  ctx -> handler.handleAttribution(ctx, "codex", "health", 2, 1, "response"));
              config.routes.get(
                  "/child",
                  ctx ->
                      handler.handleSubagentAttribution(
                          ctx, "codex", "health", "synthetic-child", 1, "response"));
              config.routes.get(
                  "/wrong-child",
                  ctx ->
                      handler.handleSubagentAttribution(
                          ctx, "codex", "health", "different-child", 1, "response"));
            }),
        (app, client) -> {
          var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
          String tail = "synthetic-" + mainCalls;
          var response = client.get("/round/2?call_id=" + tail);
          assertThat(response.code()).isEqualTo(200);
          assertThat(mapper.readTree(response.body().string()).at("/data/callId").asText())
              .isEqualTo(tail);
          assertThat(client.get("/round/1?call_id=" + tail).code()).isEqualTo(404);
          String child = "synthetic-" + (mainCalls + 2);
          response = client.get("/child?call_id=" + child);
          assertThat(response.code()).isEqualTo(200);
          assertThat(mapper.readTree(response.body().string()).at("/data/callId").asText())
              .isEqualTo(child);
          assertThat(client.get("/wrong-child?call_id=" + child).code()).isEqualTo(404);
          assertThat(client.get("/child?call_id=synthetic-1").code()).isEqualTo(404);
          assertThat(client.get("/round/2?call_id=foreign-session-call").code()).isEqualTo(404);
          assertThat(client.get("/round/2?call_id=").code()).isEqualTo(400);
        });
  }

  private static NormalizedCall call(int index, boolean child, int turn, int parent) {
    return new NormalizedCall(
        "synthetic-" + index,
        index,
        "C" + index,
        child ? CallScope.SUBAGENT : CallScope.MAIN,
        child ? Optional.of("synthetic-" + parent) : Optional.empty(),
        Optional.empty(),
        Optional.of("turn-" + turn),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(index, 0, 0, 1, index + 1),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of(),
        child ? Optional.of("synthetic-child") : Optional.empty(),
        Optional.empty());
  }
}
