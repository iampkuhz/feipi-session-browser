package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 列表页面 shell 模板静态契约测试。 */
@DisplayName("List shell template contract")
class ListShellTemplateContractTest {

  @Test
  @DisplayName("Sessions table body 不再 SSR 会话业务行")
  void sessionsRowsRenderedFromApi() {
    String template = resource("templates/sessions.html");

    assertThat(template).contains("data-api-rows=\"/api/sessions/rows\"");
    assertThat(template).contains("Session rows are loaded from /api/sessions/rows.");
    assertThat(template)
        .contains("Filters loaded from /api/sessions/active-filters")
        .contains("Loading matching sessions…");
    assertThat(template)
        .doesNotContain("{% for s in sessions %}")
        .doesNotContain("data-session-key=\"{{ s.sessionKey }}\"")
        .doesNotContain("{{ s.totalTokens | format_compact_token }}")
        .doesNotContain("{{ total_count }} matching sessions")
        .doesNotContain("{{ sessions_aggregate.totalTokens");
  }

  @Test
  @DisplayName("Projects table body 不再 SSR 项目业务行")
  void projectsRowsRenderedFromApi() {
    String template = resource("templates/projects.html");

    assertThat(template).contains("data-api-rows=\"/api/projects/rows\"");
    assertThat(template).contains("Project rows are loaded from /api/projects/rows.");
    assertThat(template)
        .contains("Loaded from /api/projects/summary")
        .contains("Loading matching projects…");
    assertThat(template)
        .doesNotContain("{% for p in projects %}")
        .doesNotContain("data-name=\"{{ p.projectName")
        .doesNotContain("{{ p.totalTokens | format_compact_token }}")
        .doesNotContain("{{ project_summary.")
        .doesNotContain("{{ total_count }} projects");
  }

  @Test
  @DisplayName("Project Detail sessions table body 不再 SSR 会话业务行")
  void projectDetailSessionRowsRenderedFromApi() {
    String template = resource("templates/project.html");

    assertThat(template)
        .contains(
            "data-api-sessions-summary=\"/api/projects/{{ project.projectKey | urlencode }}/sessions/summary\"")
        .contains(
            "data-api-sessions=\"/api/projects/{{ project.projectKey | urlencode }}/sessions/rows\"")
        .contains("Project session rows are loaded from /api/projects/{projectKey}/sessions/rows.");
    assertThat(template)
        .doesNotContain("{% for s in sessions %}")
        .doesNotContain("data-href=\"/sessions/{{ s.agent")
        .doesNotContain("{{ s_total | format_compact_token }}");
  }

  @Test
  @DisplayName("Project Detail agent mix 不再 SSR 业务行")
  void projectDetailAgentMixRenderedFromApi() {
    String template = resource("templates/project.html");

    assertThat(template)
        .contains("Agent mix rows are loaded from /api/projects/{projectKey}/agent-mix.")
        .doesNotContain("{% for agent in project_detail.agent_mix %}")
        .doesNotContain("{{ agent.tokens | format_compact_token }}")
        .doesNotContain("{{ agent.session_share | round(1) }}");
  }

  @Test
  @DisplayName("Session Detail 首屏业务数据不再 SSR")
  void sessionDetailRenderedFromApi() {
    String template = resource("templates/session.html");

    assertThat(template)
        .contains("meta")
        .contains("metrics")
        .contains("diagnostics")
        .contains("rounds")
        .contains("data-payload-sources-container")
        .contains("正在加载轮次摘要。");
    assertThat(template)
        .doesNotContain("{{ session_metrics.")
        .doesNotContain("{% for round in rounds %}")
        .doesNotContain("{% for source in payload_sources %}")
        .doesNotContain("{% for anomaly in anomaly_list %}")
        .doesNotContain("{{ anomaly_count }}");
  }

  private static String resource(String path) {
    try (var input =
        ListShellTemplateContractTest.class.getClassLoader().getResourceAsStream(path)) {
      assertThat(input).isNotNull();
      return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
