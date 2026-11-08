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
import io.javalin.testtools.JavalinTest;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class IndexSnapshotGuardTest {
  @TempDir Path directory;

  @Test
  void summaryRejectsCommitBetweenItsTwoQueriesBeforeSendingBody() throws Exception {
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
      var sessions = new SqliteSessionQueryRepository(index);
      var root =
          new QueryCompositionRoot(
              sessions,
              aggregate,
              new SqliteSessionDetailRepository(sessions),
              NormalizedArtifactLoader::load,
              3,
              QueryCache.withDefaultSize());
      var publication =
          executor.submit(
              () -> {
                assertThat(firstRead.await(10, TimeUnit.SECONDS)).isTrue();
                publish(publisher, "new");
                committed.countDown();
                return null;
              });
      var web = new WebCompositionRoot(root, WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            var response = client.get("/api/dashboard/summary");
            assertThat(response.code()).isEqualTo(409);
            assertThat(response.body().string())
                .contains("index_generation_changed")
                .doesNotContain("totalSessions");
            assertThat(response.headers().get("Cache-Control")).containsExactly("no-store");
          });
      publication.get(10, TimeUnit.SECONDS);
    }
  }

  @Test
  void warmedCacheSeesNewGenerationWithoutInvalidationAndRejectsOldExpectedHeader()
      throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("cache.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url);
        var publisher = DriverManager.getConnection(url)) {
      IndexSchema.ensureSchema(connection);
      var root = WebTestComposition.queryRoot(index, IndexSchema.CURRENT_VERSION);
      var web = new WebCompositionRoot(root, WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            var first = client.get("/api/sessions/summary");
            assertThat(first.code()).isEqualTo(200);
            assertThat(first.headers().get(IndexSnapshotGuard.HEADER)).containsExactly("legacy");
            String previous = first.headers().get(IndexSnapshotGuard.HEADER).getFirst();
            assertThat(previous).isEqualTo("legacy");
            publish(publisher, "fresh");
            var fresh = client.get("/api/sessions/summary");
            assertThat(fresh.code()).isEqualTo(200);
            assertThat(fresh.headers().get(IndexSnapshotGuard.HEADER).getFirst())
                .isNotEqualTo(previous);
            assertThat(fresh.body().string()).contains("\"totalCount\":1");
            var stale =
                client.get(
                    "/api/sessions/summary",
                    request -> request.header(IndexSnapshotGuard.HEADER, previous));
            assertThat(stale.code()).isEqualTo(409);
            assertThat(stale.body().string()).contains("index_generation_changed");
          });
      String published = root.publishedGeneration();
      var writer = new SqliteIndexWriter(publisher);
      long failed = writer.startScan(2, "incremental");
      writer.failScan(failed, 3, Map.of());
      assertThat(root.publishedGeneration()).isEqualTo(published);
    }
  }

  private static void publish(java.sql.Connection connection, String id) throws Exception {
    var writer = new SqliteIndexWriter(connection);
    long scan = writer.startScan(0, "incremental");
    try (var statement =
        connection.prepareStatement(
            "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at) VALUES (?, 'codex', ?, '', '')")) {
      statement.setString(1, "codex:" + id);
      statement.setString(2, id);
      statement.executeUpdate();
    }
    writer.completeScan(scan, 1, Map.of());
  }
}
