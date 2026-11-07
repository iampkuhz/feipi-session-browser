package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class InitialPageSnapshotGuardTest {
  @Test
  void stablePageUsesRequestGenerationAndEscapesItsHtmlAttribute() {
    String generation = "published\"<&>";
    var guard = new IndexSnapshotGuard(() -> generation);
    var templates = new PebbleEnvironment();
    var app =
        Javalin.create(
            config ->
                config.routes.get(
                    "/",
                    guard.wrapPage(
                        context -> {
                          String stamp = context.attribute(IndexSnapshotGuard.PAGE_GENERATION);
                          context.html(
                              templates.render(
                                  "base.html", Map.of(IndexSnapshotGuard.PAGE_GENERATION, stamp)));
                        })));
    JavalinTest.test(
        app,
        (server, client) -> {
          var response = client.get("/");
          assertThat(response.code()).isEqualTo(200);
          assertThat(response.headers().get(IndexSnapshotGuard.HEADER)).containsExactly(generation);
          assertThat(response.headers().get("Cache-Control").getFirst())
              .contains("no-store", "no-cache", "must-revalidate");
          assertThat(response.body().string())
              .contains("data-index-generation=\"published&quot;&lt;&amp;&gt;\"")
              .doesNotContain("data-index-generation=\"" + generation + "\"");
        });
  }

  @Test
  void continuallyChangingPublicationFailsClosedWithoutRetryingOrLeakingBusinessHtml() {
    var observations = new AtomicInteger();
    var calls = new AtomicInteger();
    var guard = new IndexSnapshotGuard(() -> "generation-" + observations.incrementAndGet());
    var app =
        Javalin.create(
            config ->
                config.routes.get(
                    "/",
                    guard.wrapPage(
                        context -> {
                          calls.incrementAndGet();
                          context.html("<section data-dashboard-kpis>mixed business 123</section>");
                        })));
    JavalinTest.test(
        app,
        (server, client) -> {
          var response = client.get("/");
          assertThat(response.code()).isEqualTo(409);
          assertThat(response.headers().get("Content-Type").getFirst()).contains("text/html");
          assertThat(response.headers().get(IndexSnapshotGuard.HEADER)).isNull();
          assertThat(response.body().string())
              .contains("index_generation_changed", "重试")
              .doesNotContain("data-dashboard-kpis", "mixed business", "123");
          assertThat(calls).hasValue(1);
          assertThat(observations).hasValue(2);
        });
  }

  @Test
  void staleExpectedGenerationNeverRunsThePageHandler() {
    var calls = new AtomicInteger();
    var guard = new IndexSnapshotGuard(() -> "new");
    var app =
        Javalin.create(
            config ->
                config.routes.get(
                    "/",
                    guard.wrapPage(
                        context -> {
                          calls.incrementAndGet();
                          context.html("business data");
                        })));
    JavalinTest.test(
        app,
        (server, client) -> {
          var response =
              client.get("/", request -> request.header(IndexSnapshotGuard.HEADER, "old"));
          assertThat(response.code()).isEqualTo(409);
          assertThat(response.body().string())
              .contains("index_generation_changed")
              .doesNotContain("business data");
          assertThat(calls).hasValue(0);
        });
  }
}
