package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.ImportedSessionAnalysis;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportPort;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.web.IndexSnapshotGuard;
import com.feipi.session.browser.web.WebTestComposition;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** synthetic：实际 normal/import handler 的显式窗口、安全边界与错误契约。 */
class SessionLocalResultPayloadTest {
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final String NORMAL = "/api/sessions/codex/synthetic";
  private static final String IMPORT_ID = "11111111-2222-4333-8444-555555555555";
  private static final String IMPORT = "/api/imports/" + IMPORT_ID;
  private static final String TOOL = "/payload/tool:result:t?view=local_results";
  @TempDir Path directory;

  @Test
  void signedHandlesRejectTamperingScopeGenerationAndUnboundedInput() {
    String token = SessionContentCursor.seal("scope", "g1", List.of("synthetic"));
    assertThat(SessionContentCursor.open(token, "scope", "g1")).containsExactly("synthetic");
    assertThatThrownBy(() -> SessionContentCursor.open(token, "other", "g1"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> SessionContentCursor.open(token, "scope", "g2"))
        .isInstanceOf(SessionContentCursor.StaleHandleException.class);
    for (String invalid : List.of("", "!", token + "x", "A".repeat(8193), "AA.AA")) {
      assertThatThrownBy(() -> SessionContentCursor.open(invalid, "scope", "g1"))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void normalAndImportReturnExactPostTwentyWindowAndKeepLegacyFullText() throws Exception {
    try (var fixture = fixture(artifact(false))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String base : List.of(NORMAL, IMPORT)) {
              var legacy = client.get(base + "/payload/tool:result:t");
              assertThat(legacy.code()).isEqualTo(200);
              JsonNode old = JSON.readTree(legacy.body().string());
              assertThat(old.has("localResults")).isFalse();
              assertThat(old.path("text").asText()).contains("SAME", "TAIL");
              var first = client.get(base + TOOL);
              assertThat(first.code()).isEqualTo(200);
              String raw = first.body().string();
              JsonNode page = JSON.readTree(raw);
              assertThat(raw).doesNotContain("contextKey", "source_unit", "synthetic.jsonl");
              assertThat(page.at("/localResults/items")).hasSize(4);
              assertThat(page.at("/payload/text").asText()).isEqualTo(old.path("text").asText());
              JsonNode preview = page.at("/localResults/items/0/targetPreview");
              assertThat(preview.path("targets")).hasSize(1);
              assertThat(preview.at("/targets/0/recordIndex").asInt()).isEqualTo(2);
              assertThat(preview.at("/targets/0/scope").asText()).isEqualTo("main");
              assertThat(
                      page.at("/localResults/items/1/targetPreview/targets/0/recordIndex").asInt())
                  .isEqualTo(3);
              assertThat(page.at("/localResults/items/2/targetPreview/targets")).isEmpty();
              assertThat(page.at("/localResults/items/2/targetPreview/coverage").asText())
                  .isEqualTo("complete");
              JsonNode previewInput =
                  read(
                      client
                          .get(
                              preview.at("/targets/0/apiUrl").asText()
                                  + "?view=local_results&target="
                                  + preview.at("/targets/0/target").asText())
                          .body()
                          .string());
              assertThat(previewInput.at("/localResults/targetReferenceId").asText())
                  .isEqualTo(preview.at("/targets/0/referenceId").asText());
              for (JsonNode input : previewInput.at("/localResults/items"))
                assertThat(input.path("targetPreview").isNull()).isTrue();
              var seen = new java.util.LinkedHashSet<String>();
              seen.add(preview.at("/targets/0/referenceId").asText());
              String previewCursor = preview.path("nextCursor").asText();
              long previewOffset = 1;
              while (previewCursor != null) {
                JsonNode remaining =
                    read(
                        client
                            .get(
                                base
                                    + TOOL
                                    + "&occurrence="
                                    + page.at("/localResults/items/0/occurrence").asText()
                                    + "&cursor="
                                    + previewCursor)
                            .body()
                            .string());
                assertThat(remaining.at("/relations/offset").asLong()).isEqualTo(previewOffset);
                for (JsonNode item : remaining.at("/relations/targets"))
                  assertThat(seen.add(item.path("referenceId").asText())).isTrue();
                previewOffset += remaining.at("/relations/targets").size();
                previewCursor =
                    remaining.at("/relations/nextCursor").isNull()
                        ? null
                        : remaining.at("/relations/nextCursor").asText();
              }
              assertThat(seen).hasSize(45);
              String occurrence = page.at("/localResults/items/0/occurrence").asText();
              String other = page.at("/localResults/items/1/occurrence").asText();
              assertThat(other).isNotEqualTo(occurrence);
              assertThat(page.at("/localResults/items/2/content/state").asText())
                  .isEqualTo("available");
              assertThat(page.at("/localResults/items/2/content/text").asText()).isEmpty();
              String relationUrl = base + TOOL + "&occurrence=" + occurrence;
              JsonNode relations = read(client.get(relationUrl).body().string());
              assertThat(relations.at("/relations/targets")).hasSize(20);
              assertThat(relations.at("/relations/coverage").asText()).isEqualTo("complete");
              assertThat(relations.path("payload").isNull()).isTrue();
              String cursor = relations.at("/relations/nextCursor").asText();
              JsonNode second = read(client.get(relationUrl + "&cursor=" + cursor).body().string());
              assertThat(second.at("/relations/offset").asInt()).isEqualTo(20);
              JsonNode last =
                  read(
                      client
                          .get(
                              relationUrl
                                  + "&cursor="
                                  + second.at("/relations/nextCursor").asText())
                          .body()
                          .string());
              assertThat(last.at("/relations/targets")).hasSize(5);
              assertThat(last.at("/relations/nextCursor").isNull()).isTrue();
              String target = last.at("/relations/targets/4/target").asText();
              String targetUrl = last.at("/relations/targets/4/apiUrl").asText();
              assertThat(targetUrl).startsWith(base + "/payload/");
              JsonNode exact =
                  read(
                      client
                          .get(targetUrl + "?view=local_results&target=" + target)
                          .body()
                          .string());
              assertThat(exact.at("/localResults/offset").asInt()).isEqualTo(40);
              assertThat(exact.at("/localResults/items")).hasSize(5);
              assertThat(exact.at("/localResults/targetReferenceId").asText())
                  .isEqualTo(last.at("/relations/targets/4/referenceId").asText());
              JsonNode otherRelations =
                  read(client.get(base + TOOL + "&occurrence=" + other).body().string());
              assertThat(otherRelations.at("/relations/targets")).hasSize(1);
              assertThat(otherRelations.at("/relations/targets/0/callId").asText()).isEqualTo("c3");
              String eof = page.at("/localResults/items/2/occurrence").asText();
              JsonNode empty = read(client.get(base + TOOL + "&occurrence=" + eof).body().string());
              assertThat(empty.at("/relations/coverage").asText()).isEqualTo("complete");
              assertThat(empty.at("/relations/targets")).isEmpty();
              assertThat(client.get(base + TOOL + "&limit=101").code()).isEqualTo(400);
              assertThat(client.get(base + TOOL + "&limit=0").code()).isEqualTo(400);
              assertThat(client.get(base + TOOL + "&occurrence=bad").code()).isEqualTo(400);
              assertThat(client.get(base + TOOL + "&occurrence=" + occurrence + "&limit=10").code())
                  .isEqualTo(400);
              assertThat(
                      client
                          .get(base + TOOL + "&occurrence=" + occurrence + "&visibility=full")
                          .code())
                  .isEqualTo(400);
              assertThat(
                      client
                          .get(base + "/payload/main:req:c3?view=local_results&target=" + target)
                          .code())
                  .isEqualTo(400);
              assertThat(client.get(base + TOOL + "&cursor=" + cursor).code()).isEqualTo(400);
              assertThat(
                      client.get(base + TOOL + "&occurrence=" + other + "&cursor=" + cursor).code())
                  .isEqualTo(400);
              String crossed = base.equals(NORMAL) ? IMPORT : NORMAL;
              assertThat(client.get(crossed + TOOL + "&occurrence=" + occurrence).code())
                  .isEqualTo(400);
            }
          });
    }
  }

  @Test
  void maskingMissingUnknownAndPartialAreNotEmptySuccessOrTruncation() throws Exception {
    try (var fixture = fixture(artifact(true))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String base : List.of(NORMAL, IMPORT)) {
              JsonNode standard = read(client.get(base + TOOL).body().string());
              JsonNode full = read(client.get(base + TOOL + "&visibility=full").body().string());
              assertThat(standard.at("/localResults/items/3/content/text").asText())
                  .doesNotContain("SYNTHETIC_ONLY");
              assertThat(full.at("/localResults/items/3/content/text").asText())
                  .contains("SYNTHETIC_ONLY");
              assertThat(standard.at("/localResults/items/3/content/truncated").asBoolean())
                  .isFalse();
              String occurrence = standard.at("/localResults/items/0/occurrence").asText();
              JsonNode relations =
                  read(client.get(base + TOOL + "&occurrence=" + occurrence).body().string());
              assertThat(relations.at("/relations/coverage").asText()).isEqualTo("partial");
              assertThat(standard.at("/localResults/items/0/targetPreview/coverage").asText())
                  .isEqualTo("partial");
              JsonNode missing =
                  read(
                      client.get(base + "/payload/main:req:c4?view=local_results").body().string());
              assertThat(missing.at("/localResults/items/0/content/state").asText())
                  .isEqualTo("missing");
              assertThat(missing.at("/localResults/items/0/occurrence").asText()).isEmpty();
              assertThat(client.get(base + "/payload/main:req:absent?view=local_results").code())
                  .isEqualTo(404);
            }
          });
    }
  }

  @Test
  void generationCrossingAndReadFailureAreExplicitAndRetryUsesSameOriginalRoute() throws Exception {
    try (var fixture = fixture(artifact(false))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            JsonNode page = read(client.get(NORMAL + TOOL).body().string());
            String occurrence = page.at("/localResults/items/0/occurrence").asText();
            JsonNode imported = read(client.get(IMPORT + TOOL).body().string());
            String importOccurrence = imported.at("/localResults/items/0/occurrence").asText();
            fixture.generation().set("g2");
            assertThat(client.get(IMPORT + TOOL + "&occurrence=" + importOccurrence).code())
                .isEqualTo(200);
            var stale = client.get(NORMAL + TOOL + "&occurrence=" + occurrence);
            assertThat(stale.code()).isEqualTo(409);
            fixture.failReads().set(true);
            var failed = client.get(NORMAL + TOOL);
            assertThat(failed.code()).isEqualTo(500);
            assertThat(failed.body().string())
                .contains("artifact_error")
                .doesNotContain("synthetic.jsonl");
            fixture.failReads().set(false);
            assertThat(client.get(NORMAL + TOOL).code()).isEqualTo(200);
          });
    }
  }

  @Test
  void unanchoredAndConflictingMirrorsExposeUnknownIdentityWithoutInventedTargets()
      throws Exception {
    for (boolean conflict : List.of(false, true)) {
      var base = artifact(false);
      var source = new LinkedHashMap<String, Object>();
      source.put("type", "tool_result");
      source.put("role", "user");
      source.put("tool_call_id", "t");
      source.put("text", "SYNTHETIC_CONFLICT_OR_UNKNOWN");
      if (conflict) source.put("result_source_unit_key", "r1");
      var calls = new ArrayList<>(base.calls());
      calls.set(1, call(2, Collections.nCopies(45, "r1"), List.of(source)));
      var altered =
          new NormalizedSessionArtifact(
              base.schemaVersion(),
              base.agent(),
              base.sourceFiles(),
              base.session(),
              calls,
              base.toolExecutions(),
              base.diagnostics(),
              base.sourceUnitCatalog(),
              base.sourceUnitSequences());
      try (var fixture = fixture(altered)) {
        JavalinTest.test(
            fixture.app(),
            (app, client) -> {
              for (String scope : List.of(NORMAL, IMPORT)) {
                JsonNode page = read(client.get(scope + TOOL).body().string());
                JsonNode item =
                    java.util.stream.StreamSupport.stream(
                            page.at("/localResults/items").spliterator(), false)
                        .filter(
                            value ->
                                value
                                    .path("identity")
                                    .asText()
                                    .equals(conflict ? "ambiguous" : "unconfirmed"))
                        .findFirst()
                        .orElseThrow(() -> new AssertionError(page.toString()));
                assertThat(item.path("identity").asText())
                    .isEqualTo(conflict ? "ambiguous" : "unconfirmed");
                assertThat(item.at("/targetPreview/coverage").asText()).isEqualTo("unknown");
                assertThat(item.at("/targetPreview/targets")).isEmpty();
                String occurrence = item.path("occurrence").asText();
                JsonNode relations =
                    read(client.get(scope + TOOL + "&occurrence=" + occurrence).body().string());
                assertThat(relations.at("/relations/coverage").asText()).isEqualTo("unknown");
                assertThat(relations.at("/relations/targets")).isEmpty();
              }
            });
      }
    }
  }

  @Test
  void oneReaderPerRequestKeepsRelationPagesMetadataOnlyAndRejectsBadTokensBeforeReplay()
      throws Exception {
    try (var fixture = fixture(artifact(false))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            int before = fixture.opens().get();
            assertThat(client.get(NORMAL + "/payload/tool:result:t").code()).isEqualTo(200);
            assertThat(fixture.opens().get() - before).isEqualTo(1);
            before = fixture.opens().get();
            JsonNode page = read(client.get(NORMAL + TOOL).body().string());
            assertThat(fixture.opens().get() - before).isEqualTo(6);
            String occurrence = page.at("/localResults/items/0/occurrence").asText();
            before = fixture.opens().get();
            JsonNode relations =
                read(client.get(NORMAL + TOOL + "&occurrence=" + occurrence).body().string());
            assertThat(fixture.opens().get() - before).isEqualTo(3);
            before = fixture.opens().get();
            read(
                client
                    .get(
                        NORMAL
                            + TOOL
                            + "&occurrence="
                            + occurrence
                            + "&cursor="
                            + relations.at("/relations/nextCursor").asText())
                    .body()
                    .string());
            assertThat(fixture.opens().get() - before).isEqualTo(3);
            before = fixture.opens().get();
            assertThat(client.get(NORMAL + TOOL + "&occurrence=bad").code()).isEqualTo(400);
            assertThat(fixture.opens().get()).isEqualTo(before);
          });
    }
  }

  @Test
  void validSignaturesStillRequireActualOccurrenceMembershipAndExactReference() throws Exception {
    try (var fixture = fixture(artifact(false))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            String absentOccurrence =
                signed("occurrence", "tool:result:t", List.of("not-recorded"));
            assertThat(client.get(NORMAL + TOOL + "&occurrence=" + absentOccurrence).code())
                .isEqualTo(404);
            String absentReference =
                signed("target", "main:req:c2", List.of("not-recorded", "not-reference"));
            assertThat(
                    client
                        .get(
                            NORMAL
                                + "/payload/main:req:c2?view=local_results&target="
                                + absentReference)
                        .code())
                .isEqualTo(404);
            JsonNode page = read(client.get(NORMAL + TOOL).body().string());
            String occurrence = page.at("/localResults/items/0/occurrence").asText();
            assertThat(
                    client
                        .get(
                            NORMAL
                                + "/payload/tool:result:other?view=local_results&occurrence="
                                + occurrence)
                        .code())
                .isEqualTo(400);
            assertThat(client.get(NORMAL + "/payload/main:resp:c1?view=local_results").code())
                .isEqualTo(404);
          });
    }
  }

  private static String signed(String kind, String payload, List<String> values) {
    var scope = new StringBuilder();
    for (String part : List.of(NORMAL, "standard", "20", kind, payload, ""))
      scope.append(part.length()).append(':').append(part);
    return SessionContentCursor.seal(scope.toString(), "g1|synthetic-content", values);
  }

  @Test
  void missingOccurrenceDoesNotChangeLegacyToolLevelPresenceStatus() throws Exception {
    var base = artifact(false);
    var missing = new LinkedHashMap<String, SourceUnitCatalogEntry>();
    for (int i = 1; i <= 21; i++)
      missing.put(
          "r" + i,
          new SourceUnitCatalogEntry(
              "r" + i,
              "synthetic.jsonl",
              "synthetic#event[" + i + "]",
              "tool_result",
              "",
              SourceUnitDirection.REQUEST,
              i,
              0,
              ByteRange.empty(),
              "",
              Optional.empty(),
              Optional.of("t"),
              50,
              Optional.empty(),
              Optional.empty(),
              Map.of("type", "tool_result", "tool_call_id", "t"),
              Optional.empty(),
              Optional.empty(),
              List.of()));
    var altered =
        new NormalizedSessionArtifact(
            base.schemaVersion(),
            base.agent(),
            base.sourceFiles(),
            base.session(),
            List.of(call(1, List.of())),
            base.toolExecutions(),
            List.of(),
            missing,
            Map.of());
    try (var fixture = fixture(altered)) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String scope : List.of(NORMAL, IMPORT)) {
              JsonNode legacy = read(client.get(scope + "/payload/tool:result:t").body().string());
              JsonNode typed = read(client.get(scope + TOOL).body().string());
              assertThat(typed.at("/localResults/items/0/content/state").asText())
                  .isEqualTo("missing");
              assertThat(typed.at("/payload/status").asText())
                  .isEqualTo(legacy.path("status").asText());
              assertThat(typed.at("/payload/text").asText())
                  .isEqualTo(legacy.path("text").asText());
              JsonNode next =
                  read(
                      client
                          .get(
                              scope
                                  + TOOL
                                  + "&cursor="
                                  + typed.at("/localResults/nextCursor").asText())
                          .body()
                          .string());
              assertThat(next.at("/localResults/offset").asInt()).isEqualTo(20);
              assertThat(next.at("/localResults/items")).hasSize(1);
              assertThat(next.at("/localResults/items/0/content/state").asText())
                  .isEqualTo("missing");
              assertThat(next.at("/payload/status").asText())
                  .isEqualTo(legacy.path("status").asText());
              assertThat(next.at("/payload/text").asText()).isEqualTo(legacy.path("text").asText());
            }
          });
    }
  }

  @Test
  void targetPreviewBudgetCoversAtMostTwentyResultsWithoutPretendingUnloadedIsEmpty()
      throws Exception {
    try (var fixture = fixture(artifact(false, 100))) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String base : List.of(NORMAL, IMPORT)) {
              for (int limit : List.of(21, 100)) {
                JsonNode page = read(client.get(base + TOOL + "&limit=" + limit).body().string());
                assertThat(page.at("/localResults/items")).hasSize(limit);
                int loaded = 0;
                int targets = 0;
                for (JsonNode item : page.at("/localResults/items")) {
                  JsonNode preview = item.path("targetPreview");
                  if (!preview.isNull()) {
                    loaded++;
                    targets += preview.path("targets").size();
                  }
                }
                assertThat(loaded).isEqualTo(20);
                assertThat(targets).isLessThanOrEqualTo(20);
                assertThat(page.at("/localResults/items/19/targetPreview/coverage").asText())
                    .isEqualTo("complete");
                assertThat(page.at("/localResults/items/19/targetPreview/targets")).isEmpty();
                assertThat(page.at("/localResults/items/20/targetPreview").isNull()).isTrue();
                assertThat(page.at("/localResults/items/20/occurrence").asText()).isNotBlank();
              }
            }
          });
    }
  }

  @Test
  void exactAttributionPathUsesFullIdentityAndActualLaterRoundWithoutOrdinalGuessing()
      throws Exception {
    var base = artifact(false);
    var calls = new ArrayList<NormalizedCall>();
    for (var call : base.calls())
      calls.add(
          identityCall(
              call,
              call.callIndex() == 3 ? "synthetic:c3/full id" : call.callId(),
              CallScope.MAIN));
    var altered =
        new NormalizedSessionArtifact(
            base.schemaVersion(),
            base.agent(),
            base.sourceFiles(),
            base.session(),
            calls,
            base.toolExecutions(),
            base.diagnostics(),
            base.sourceUnitCatalog(),
            base.sourceUnitSequences());
    try (var fixture = fixture(altered)) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String scope : List.of(NORMAL, IMPORT)) {
              JsonNode page = read(client.get(scope + TOOL).body().string());
              for (int i = 0; i < 2; i++) {
                JsonNode target = page.at("/localResults/items/" + i + "/targetPreview/targets/0");
                String path = target.path("attributionPath").asText();
                assertThat(path).startsWith("/attribution/call/").endsWith("/request");
                JsonNode attribution = read(client.get(scope + path).body().string());
                assertThat(attribution.path("callIndex").asInt()).isEqualTo(i + 2);
                assertThat(attribution.path("roundIndex").asInt()).isEqualTo(i + 2);
                assertThat(attribution.at("/data/callId").asText())
                    .isEqualTo(i == 0 ? "c2" : "synthetic:c3/full id");
                assertThat(attribution.at("/data/scope").asText()).isEqualTo("main");
              }
              assertThat(client.get(scope + "/attribution/call/missing/request").code())
                  .isEqualTo(404);
              assertThat(client.get(scope + "/attribution/call/c2/bad-kind").code()).isEqualTo(400);
              assertThat(client.get(scope + "/attribution/1/1/request?call_id=c2").code())
                  .isEqualTo(404);
              assertThat(client.get(scope + "/attribution/call/c2/response").code()).isEqualTo(200);
            }
          });
    }
  }

  @Test
  void exactAttributionIdentityPreservesActualChildScope() throws Exception {
    var base = artifact(false);
    var calls = new ArrayList<>(base.calls());
    calls.set(2, identityCall(calls.get(2), "synthetic-child/full id", CallScope.SUBAGENT));
    var altered =
        new NormalizedSessionArtifact(
            base.schemaVersion(),
            base.agent(),
            base.sourceFiles(),
            base.session(),
            calls,
            base.toolExecutions(),
            base.diagnostics(),
            base.sourceUnitCatalog(),
            base.sourceUnitSequences());
    try (var fixture = fixture(altered)) {
      JavalinTest.test(
          fixture.app(),
          (app, client) -> {
            for (String scope : List.of(NORMAL, IMPORT)) {
              JsonNode response =
                  read(
                      client
                          .get(
                              scope
                                  + "/attribution/call/"
                                  + ApiQueryParams.url("synthetic-child/full id")
                                  + "/request")
                          .body()
                          .string());
              assertThat(response.at("/data/callId").asText()).isEqualTo("synthetic-child/full id");
              assertThat(response.at("/data/scope").asText()).isEqualTo("subagent");
              assertThat(response.path("callIndex").asInt()).isEqualTo(3);
              assertThat(response.path("roundIndex").asInt()).isPositive();
            }
          });
    }
  }

  private static NormalizedCall identityCall(NormalizedCall call, String id, CallScope scope) {
    return new NormalizedCall(
        id,
        call.callIndex(),
        call.callKey(),
        scope,
        scope == CallScope.SUBAGENT ? Optional.of("c1") : Optional.empty(),
        scope == CallScope.SUBAGENT ? Optional.of("t") : Optional.empty(),
        Optional.of("synthetic-turn-" + call.callIndex()),
        call.model(),
        call.timestamp(),
        call.usage(),
        call.request(),
        call.response(),
        call.sourceUnitRefRanges(),
        call.sourceUnits(),
        Map.of(),
        Map.of(),
        scope == CallScope.SUBAGENT ? Optional.of("synthetic-child") : Optional.empty(),
        Optional.empty());
  }

  private static JsonNode read(String body) throws IOException {
    JsonNode response = JSON.readTree(body);
    assertThat(response.has("error")).as(body).isFalse();
    return response;
  }

  private Fixture fixture(NormalizedSessionArtifact artifact) throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("synthetic-" + UUID.randomUUID() + ".db");
    var index = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    IndexSchema.ensureSchema(index.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(index);
    var row =
        WebTestComposition.queryRoot(index, IndexSchema.CURRENT_VERSION)
            .sessionDetail()
            .getDetailContext("claude_code:s-alpha-001", PayloadVisibility.STANDARD)
            .orElseThrow()
            .detail()
            .sessionRow();
    var generation = new AtomicReference<>("g1");
    var fail = new java.util.concurrent.atomic.AtomicBoolean();
    var opens = new AtomicInteger();
    var source = NormalizedSessionContent.fromArtifact(artifact);
    NormalizedSessionContent counted =
        new NormalizedSessionContent() {
          @Override
          public NormalizedContentHeader header() {
            return source.header();
          }

          @Override
          public ContentCursor openCursor() throws IOException {
            opens.incrementAndGet();
            if (fail.get()) throw new IOException("synthetic read failure");
            return source.openCursor();
          }
        };
    var service =
        new SessionApiService(
            (key, visibility) ->
                Optional.of(
                    new SessionDetailUseCase.DetailContext(
                        new SessionDetail(
                            row, List.of(), List.of(), visibility, "", "", "synthetic-content"),
                        artifact,
                        counted)),
            generation::get);
    var router = new SessionApiRouter(new SessionApiHandler(service));
    var imports =
        new ImportedSessionUseCase(
            new SessionImportPort() {
              private final ImportedSessionAnalysis analysis =
                  new ImportedSessionAnalysis(
                      new ImportedSessionMetadata(
                          IMPORT_ID,
                          NormalizedAgent.CODEX,
                          "synthetic.jsonl",
                          "synthetic",
                          1,
                          Instant.parse("2026-01-01T00:00:00Z")),
                      row,
                      artifact);

              @Override
              public ImportedSessionAnalysis create(
                  InputStream input, String filename, NormalizedAgent agent) {
                return analysis;
              }

              @Override
              public Optional<ImportedSessionAnalysis> find(String id) {
                return IMPORT_ID.equals(id) ? Optional.of(analysis) : Optional.empty();
              }

              @Override
              public boolean delete(String id) {
                return false;
              }

              @Override
              public ImportLimits limits() {
                return ImportLimits.defaults();
              }

              @Override
              public void close() {}
            });
    var imported = new ImportedSessionApiHandler(imports);
    var guard = new IndexSnapshotGuard(generation::get);
    var app =
        Javalin.create(
            config -> {
              config.routes.get("/api/sessions/*", guard.wrap(router::route));
              config.routes.get("/api/imports/{importId}/*", imported::handleResource);
            });
    return new Fixture(app, index, imports, generation, fail, opens);
  }

  private record Fixture(
      Javalin app,
      IndexConnection index,
      ImportedSessionUseCase imports,
      AtomicReference<String> generation,
      java.util.concurrent.atomic.AtomicBoolean failReads,
      AtomicInteger opens)
      implements AutoCloseable {
    @Override
    public void close() throws IOException {
      imports.close();
      index.close();
    }
  }

  private static NormalizedSessionArtifact artifact(boolean partial) {
    return artifact(partial, 4);
  }

  private static NormalizedSessionArtifact artifact(boolean partial, int count) {
    var refs = new ArrayList<String>(Collections.nCopies(45, "r1"));
    var calls = new ArrayList<>(List.of(call(1, List.of()), call(2, refs), call(3, List.of("r2"))));
    if (partial) calls.add(call(4, List.of("missing")));
    var entries = new LinkedHashMap<String, SourceUnitCatalogEntry>();
    for (int i = 1; i <= count; i++) {
      String text = i <= 2 ? "SAME" : i == 3 ? "" : "TAIL token=SYNTHETIC_ONLY";
      entries.put(
          "r" + i,
          new SourceUnitCatalogEntry(
              "r" + i,
              "synthetic.jsonl",
              "synthetic#event[" + i + "]",
              "tool_result",
              "",
              SourceUnitDirection.REQUEST,
              i,
              0,
              ByteRange.empty(),
              "",
              Optional.empty(),
              Optional.of("t"),
              50,
              Optional.empty(),
              Optional.of(text),
              Map.of("type", "tool_result", "tool_call_id", "t"),
              Optional.empty(),
              Optional.empty(),
              List.of()));
    }
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CODEX,
        List.of(),
        Map.of("session_key", "codex:synthetic"),
        calls,
        List.of(
            new NormalizedToolExecution(
                "t",
                "synthetic-tool",
                CallScope.MAIN,
                "c1",
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                750,
                List.of(),
                Optional.empty())),
        List.of(),
        entries,
        Map.of());
  }

  private static NormalizedCall call(int i, List<String> refs) {
    return call(i, refs, List.of());
  }

  private static NormalizedCall call(int i, List<String> refs, List<Map<String, Object>> sources) {
    return new NormalizedCall(
        "c" + i,
        i,
        "C" + i,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        refs.isEmpty()
            ? List.of()
            : List.of(
                new SourceUnitRefRange(
                    Optional.empty(), 0, refs.size(), refs, Optional.of("user"))),
        sources,
        Map.of(),
        Map.of());
  }
}
