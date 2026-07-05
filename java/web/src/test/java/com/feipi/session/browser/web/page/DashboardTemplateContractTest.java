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
  @DisplayName("All Agents Tokens 单元格不渲染 tokenbar")
  void allAgentsTokensCellDoesNotRenderTokenbar() {
    String template = dashboardTemplate();
    int start = template.indexOf("<section class=\"card table-card\" aria-label=\"All Agents\">");
    assertThat(start).isNotNegative();
    int end = template.indexOf("</section>", start);
    assertThat(end).isGreaterThan(start);
    String allAgentsSection = template.substring(start, end);

    assertThat(allAgentsSection).contains("token-cell__value");
    assertThat(allAgentsSection).contains("agent.tokens_full | default(agent.tokens)");
    assertThat(allAgentsSection).contains("agent.token_full_share | default(agent.token_share)");
    assertThat(allAgentsSection).doesNotContain("tokenbar");
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
