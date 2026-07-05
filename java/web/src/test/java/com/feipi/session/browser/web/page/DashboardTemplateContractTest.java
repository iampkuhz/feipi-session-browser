package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Dashboard 模板静态契约测试。 */
@DisplayName("Dashboard template contract")
class DashboardTemplateContractTest {

  @Test
  @DisplayName("Dashboard agent tables 不再 SSR 业务行")
  void agentTablesRenderedFromApi() {
    String template = dashboardTemplate();
    int start = template.indexOf("<section class=\"card table-card\" aria-label=\"All Agents\">");
    assertThat(start).isNotNegative();
    int end = template.indexOf("</section>", start);
    assertThat(end).isGreaterThan(start);
    String allAgentsSection = template.substring(start, end);

    assertThat(allAgentsSection)
        .contains("Agent rows are loaded from /api/dashboard/agents/contribution.")
        .doesNotContain("{% for agent in all_agents_branch.agent_rows %}")
        .doesNotContain("agent.tokens_full | default(agent.tokens)");

    assertThat(template)
        .contains("Efficiency rows are loaded from /api/dashboard/agents/efficiency.")
        .doesNotContain("{% for row in all_agents_branch.efficiency_rows %}")
        .doesNotContain("row.tokens_per_session");
  }

  @Test
  @DisplayName("Dashboard 图表数据不再以内嵌 JSON script 作为数据真相")
  void chartDataNotEmbeddedAsJsonScripts() {
    String template = dashboardTemplate();

    assertThat(template)
        .doesNotContain("dashboard-graph-data")
        .doesNotContain("dashboard-prompt-data")
        .doesNotContain("dashboard-cache-health-data")
        .doesNotContain("type=\"application/json\"");
  }

  private static String dashboardTemplate() {
    try (var input =
        DashboardTemplateContractTest.class
            .getClassLoader()
            .getResourceAsStream("templates/dashboard.html")) {
      assertThat(input).isNotNull();
      return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }
}
