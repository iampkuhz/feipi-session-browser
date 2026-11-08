package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.api.query.AggregateQueryPort;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import io.javalin.testtools.JavalinTest;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class InitialPageSnapshotTest {
  @TempDir Path directory;

  @Test
  void missingLastActivityRemainsUnknownAndDoesNotCrashDashboard() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("unknown-activity.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url)) {
      IndexSchema.ensureSchema(connection);
      publish(connection);
      var aggregate = new SqliteAggregateQueryRepository(index);
      assertThat(aggregate.agentBreakdown())
          .singleElement()
          .satisfies(
              row -> {
                assertThat(row.sessionCount()).isEqualTo(1);
                assertThat(row.lastActive()).isEmpty();
              });
      JavalinTest.test(
          new WebCompositionRoot(queryRoot(index, aggregate), WebConfig.defaults()).app(),
          (app, client) -> {
            var response = client.get("/dashboard");
            assertThat(response.code()).isEqualTo(200);
            assertDashboardValues(response.body().string(), "1", "1");
          });
    }
  }

  @Test
  void dashboardNeverServesOldTotalWithNewTodayAfterPublicationBetweenQueries() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("crossing.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url);
        var publisher = DriverManager.getConnection(url);
        var executor = Executors.newSingleThreadExecutor()) {
      PragmaConfig.DEFAULTS.apply(connection);
      PragmaConfig.DEFAULTS.apply(publisher);
      IndexSchema.ensureSchema(connection);
      var firstRead = new CountDownLatch(1);
      var committed = new CountDownLatch(1);
      var delegate = new SqliteAggregateQueryRepository(index);
      var aggregate =
          (AggregateQueryPort)
              Proxy.newProxyInstance(
                  AggregateQueryPort.class.getClassLoader(),
                  new Class<?>[] {AggregateQueryPort.class},
                  (proxy, method, arguments) -> {
                    Object value = method.invoke(delegate, arguments);
                    if (method.getName().equals("dashboardStats")) {
                      firstRead.countDown();
                      assertThat(committed.await(10, TimeUnit.SECONDS)).isTrue();
                    }
                    return value;
                  });
      var root = queryRoot(index, aggregate);
      var publication =
          executor.submit(
              () -> {
                assertThat(firstRead.await(10, TimeUnit.SECONDS)).isTrue();
                publish(publisher);
                committed.countDown();
                return null;
              });
      JavalinTest.test(
          new WebCompositionRoot(root, WebConfig.defaults()).app(),
          (app, client) -> {
            var response = client.get("/dashboard");
            String html = response.body().string();
            // 先核对真实渲染的业务值，再验证页面的索引代号。
            if (response.code() == 200) {
              assertDashboardValues(html, "1", "1");
              assertThat(response.headers().get(IndexSnapshotGuard.HEADER)).isNotEmpty();
              assertGeneration(
                  html, response.headers().get(IndexSnapshotGuard.HEADER).getFirst(), root);
            } else {
              assertThat(response.code()).as("synthetic SSR response: %s", html).isIn(409, 503);
              assertThat(response.headers().get("Content-Type").getFirst()).contains("text/html");
              assertThat(html).contains("index_generation_changed");
              assertThat(html).containsPattern("(?i)retry|reload|重试");
              assertThat(html).doesNotContain("data-dashboard-kpis", "metric-card__value");
            }
            assertThat(response.headers().get("Cache-Control").getFirst())
                .contains("no-store", "no-cache", "must-revalidate");
          });
      publication.get(10, TimeUnit.SECONDS);
    }
  }

  @Test
  void stableDashboardStampsItsActualInitialBusinessValuesWithPublishedGeneration()
      throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("stable.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url)) {
      IndexSchema.ensureSchema(connection);
      publish(connection);
      var root = queryRoot(index, new SqliteAggregateQueryRepository(index));
      // 直接执行全部页面查询，避免把测试数据错误误认成快照失败回归。
      var dashboard = root.dashboard();
      assertThat(dashboard.stats(AgentFilter.NONE).totalSessions()).isEqualTo(1);
      assertThat(dashboard.kpiSupplement(AgentFilter.NONE).todaySessions()).isEqualTo(1);
      assertThat(dashboard.trendData(TrendFilter.ofDays(30))).hasSize(1);
      dashboard.activityTrend(TrendFilter.ofDays(30));
      dashboard.agentEfficiency();
      dashboard.agentBreakdown();
      JavalinTest.test(
          new WebCompositionRoot(root, WebConfig.defaults()).app(),
          (app, client) -> {
            var response = client.get("/dashboard");
            String html = response.body().string();
            assertThat(response.code()).as("synthetic SSR response: %s", html).isEqualTo(200);
            assertDashboardValues(html, "1", "1");
            assertThat(response.headers().get(IndexSnapshotGuard.HEADER)).isNotEmpty();
            assertGeneration(
                html, response.headers().get(IndexSnapshotGuard.HEADER).getFirst(), root);
            assertThat(response.headers().get("Cache-Control").getFirst())
                .contains("no-store", "no-cache", "must-revalidate");
          });
    }
  }

  private static QueryCompositionRoot queryRoot(
      IndexConnection index, AggregateQueryPort aggregate) {
    var sessions = new SqliteSessionQueryRepository(index);
    return new QueryCompositionRoot(
        sessions,
        aggregate,
        new SqliteSessionDetailRepository(sessions),
        NormalizedArtifactLoader::load,
        IndexSchema.CURRENT_VERSION.version(),
        QueryCache.withDefaultSize());
  }

  private static void assertDashboardValues(String html, String total, String today) {
    var card =
        Pattern.compile(
                "<article\\b[^>]*aria-label=\"Sessions\"[^>]*>(.*?)</article>", Pattern.DOTALL)
            .matcher(html);
    assertThat(card.find()).as("SSR Sessions card exists").isTrue();
    String sessions = card.group(1);
    assertThat(sessions)
        .containsPattern("(?s)data-kpi-tooltip=\"Sessions\"[^>]*>\\s*" + total + "\\s*</span>");
    assertThat(sessions)
        .containsPattern(
            "(?s)metric-card__secondary-label\">Today</span>\\s*"
                + "<span class=\"metric-card__secondary-value\">\\s*"
                + today
                + "\\s*</span>");
  }

  private static void assertGeneration(String html, String header, QueryCompositionRoot root) {
    assertThat(header).isNotBlank().isEqualTo(root.publishedGeneration());
    assertThat(html)
        .containsPattern("<body\\b[^>]*\\bdata-index-generation=\"" + Pattern.quote(header) + "\"");
  }

  private static void publish(Connection connection) throws Exception {
    var writer = new SqliteIndexWriter(connection);
    long scan = writer.startScan(0, "incremental");
    // 使用数据库的当前 UTC 时间，保证与当日统计采用相同日期且不落入未来。
    try (var statement = connection.createStatement()) {
      statement.executeUpdate(
          "INSERT INTO sessions(session_key, agent, session_id, project_key, started_at, ended_at) "
              + "VALUES ('codex:synthetic', 'codex', 'synthetic', '', "
              + "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), '')");
    }
    writer.completeScan(scan, 1, Map.of());
  }
}
