package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.api.query.AggregateQueryPort;
import com.feipi.session.browser.index.api.query.EventActivity;
import com.feipi.session.browser.index.api.query.EventActivity.Day;
import com.feipi.session.browser.index.api.query.EventActivity.TokenComponent;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 独立事件日 API 的 synthetic HTTP 契约，不依赖真实来源或 artifact。 */
class DashboardEventActivityApiTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  @TempDir Path directory;
  private IndexConnection index;
  private final AtomicReference<TrendFilter> received = new AtomicReference<>();

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("event-activity.db");
    index = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    IndexSchema.ensureSchema(index.writerConnection());
  }

  @AfterEach
  void close() {
    index.close();
  }

  @Test
  void returnsIndependentDaysCoverageAndNullableAmountsWithExactFilter() {
    JavalinTest.test(
        web(fixture()).app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/event-activity?agent=claude-code&days=17");
          assertThat(response.code()).isEqualTo(200);
          var body = MAPPER.readTree(response.body().string());
          assertThat(body.path("basis").asText()).isEqualTo("source_event_utc");
          assertThat(body.path("tokenBasis").asText()).isEqualTo("codex_modern_usage_report_day");
          assertThat(body.path("coverage").asText()).isEqualTo("partial");
          assertThat(body.path("windowDays").asInt()).isEqualTo(17);
          assertThat(body.path("days"))
              .isEqualTo(MAPPER.readTree(MAPPER.writeValueAsBytes(fixture().days())));
          assertThat(body.path("coverageCounts"))
              .isEqualTo(MAPPER.readTree(MAPPER.writeValueAsBytes(fixture().coverage())));
          assertThat(body.path("undatedTokens"))
              .isEqualTo(MAPPER.readTree(MAPPER.writeValueAsBytes(fixture().undatedTokens())));
          assertThat(body.at("/days/0/tokens/fresh/reportedTokens").isNull()).isTrue();
          assertThat(body.at("/days/0/tokens/cacheRead/reportedTokens").asLong()).isZero();
          assertThat(received.get().days()).isEqualTo(17);
          assertThat(received.get().agentFilter().agent()).isEqualTo("claude_code");
        });
  }

  @Test
  void oldIndexWithoutSummariesIsUnknownNotMeasuredZero() {
    var unknown =
        new EventActivity(
            List.of(), Map.of("summarizedSessions", 0L, "unknownSessions", 4L), components());
    JavalinTest.test(
        web(unknown).app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/event-activity?agent=all&days=30");
          assertThat(response.code()).isEqualTo(200);
          var body = MAPPER.readTree(response.body().string());
          assertThat(body.path("coverage").asText()).isEqualTo("unknown");
          assertThat(body.path("days")).isEmpty();
          assertThat(body.at("/undatedTokens/fresh/reportedTokens").isNull()).isTrue();
          assertThat(received.get().agentFilter().isUnfiltered()).isTrue();
        });
  }

  @Test
  void rejectsInvalidFiltersWithoutQuerying() {
    JavalinTest.test(
        web(fixture()).app(),
        (app, client) -> {
          for (String query :
              List.of("agent=not-an-agent", "days=0", "days=-1", "days=abc", "days=2147483648")) {
            assertThat(client.get("/api/dashboard/event-activity?" + query).code()).isEqualTo(400);
          }
          assertThat(received.get()).isNull();
        });
  }

  @Test
  void unavailablePortReturnsSafe501RatherThanEmptySuccess() {
    JavalinTest.test(
        web(null).app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/event-activity?days=30");
          assertThat(response.code()).isEqualTo(501);
          assertThat(response.body().string())
              .contains("EVENT_ACTIVITY_UNAVAILABLE")
              .doesNotContain("synthetic-private-detail");
        });
  }

  @Test
  void staleGenerationIsRejectedBeforeEventQuery() {
    JavalinTest.test(
        web(fixture()).app(),
        (app, client) -> {
          var response =
              client.get(
                  "/api/dashboard/event-activity?days=30",
                  request -> request.header("X-Session-Index-Generation", "synthetic-stale"));
          assertThat(response.code()).isEqualTo(409);
          assertThat(received.get()).isNull();
        });
  }

  private WebCompositionRoot web(EventActivity result) {
    var delegate = new SqliteAggregateQueryRepository(index);
    var aggregate =
        (AggregateQueryPort)
            Proxy.newProxyInstance(
                AggregateQueryPort.class.getClassLoader(),
                new Class<?>[] {AggregateQueryPort.class},
                (proxy, method, args) -> {
                  if (method.getName().equals("eventActivity")) {
                    received.set((TrendFilter) args[0]);
                    if (result == null) {
                      throw new UnsupportedOperationException("synthetic-private-detail");
                    }
                    return result;
                  }
                  return method.invoke(delegate, args);
                });
    var sessions = new SqliteSessionQueryRepository(index);
    var root =
        new QueryCompositionRoot(
            sessions,
            aggregate,
            new SqliteSessionDetailRepository(sessions),
            NormalizedArtifactLoader::load,
            1,
            QueryCache.withDefaultSize());
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static EventActivity fixture() {
    return new EventActivity(
        List.of(new Day("2026-11-03", 2, components()), new Day("2026-11-04", 3, components())),
        Map.of(
            "summarizedSessions",
            2L,
            "unknownSessions",
            1L,
            "undatedUserMessages",
            4L,
            "undatedUsageEvents",
            5L,
            "unsupportedUsageEvents",
            6L,
            "futureExcludedDayBuckets",
            1L,
            "futureExcludedObservedUserMessages",
            7L),
        components());
  }

  private static Map<String, TokenComponent> components() {
    return Map.of(
        "fresh",
        new TokenComponent(null, 0, 1, 2, 3, 4),
        "cacheRead",
        new TokenComponent(0L, 1, 0, 0, 0, 0),
        "cacheWrite",
        new TokenComponent(11L, 2, 3, 4, 5, 6),
        "output",
        new TokenComponent(13L, 1, 0, 0, 0, 0));
  }
}
