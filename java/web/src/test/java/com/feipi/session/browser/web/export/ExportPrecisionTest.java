package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/** 完全 synthetic 的离线导出精度与资源契约。 */
class ExportPrecisionTest {

  @Test
  void estimatedTokensDoNotTurnMissingCacheIntoMeasuredZero() {
    String html =
        render(
            new TokenProvenance(
                "estimated", "unavailable", "unavailable", "estimated", "synthetic", 1, 1, 0),
            SessionTiming.unknown(null));

    assertThat(metric(html, "total")).contains("≈", "Partial", "Estimated");
    assertThat(metric(html, "freshInput")).contains("≈", "Estimated");
    assertThat(metric(html, "output")).contains("≈", "Estimated");
    assertThat(metric(html, "cacheRead")).isEqualTo("Not reported");
    assertThat(metric(html, "cacheWrite")).isEqualTo("Not reported");
    assertThat(metric(html, "duration")).contains("Unknown").doesNotContain("0s");
    assertThat(html).doesNotContain("style=\"--seg-pct:");
  }

  @Test
  void providerReportedZeroRemainsAnActualZero() {
    String html =
        render(
            new TokenProvenance(
                "provider_reported",
                "provider_reported",
                "provider_reported",
                "provider_reported",
                "",
                0,
                0,
                0),
            timing(60.0, "measured"));

    assertThat(metric(html, "cacheRead")).isEqualTo("0");
    assertThat(metric(html, "total")).doesNotContain("Estimated", "Partial", "Unknown");
    assertThat(metric(html, "duration")).doesNotContain("Unknown", "Not reported");
    assertThat(html).contains("style=\"--seg-pct:");
  }

  @Test
  void legacyUnknownValuesAreNotGuessedFromAgentName() {
    String html = render(TokenProvenance.unknown(), SessionTiming.unknown(null));

    assertThat(metric(html, "total")).contains("Unknown");
    assertThat(metric(html, "cacheRead")).isEqualTo("N/A · Unknown");
    assertThat(metric(html, "cacheWrite")).isEqualTo("N/A · Unknown");
    assertThat(html).doesNotContain("style=\"--seg-pct:");
  }

  @Test
  void mixedProvenanceRetainsItsPartialStatus() {
    String html =
        render(
            new TokenProvenance("mixed", "mixed", "mixed", "mixed", "synthetic", 1, 1, 1),
            SessionTiming.unknown(null));

    assertThat(metric(html, "total")).contains("Partial");
    assertThat(metric(html, "freshInput")).contains("Partial");
    assertThat(metric(html, "cacheRead")).isEqualTo("N/A · Partial · Estimated");
    assertThat(metric(html, "duration")).isEqualTo("N/A · Unknown");
    assertThat(html).contains("Unknown source", "Not reported", "Estimated");
  }

  @Test
  void partialWallDurationIsNotPresentedAsAnExactMeasurement() {
    String html = render(TokenProvenance.unknown(), timing(60.0, "partial"));

    assertThat(metric(html, "duration")).contains("Partial").doesNotContain("Unknown");
  }

  @Test
  void exportRemainsSelfContainedAutoescapedAndVisibilityAware() {
    String html = render(TokenProvenance.unknown(), SessionTiming.unknown(null));

    assertThat(html)
        .startsWith("<!DOCTYPE html>")
        .contains("<style>", "&lt;synthetic-title&gt;", "Payload content is hidden")
        .doesNotContain(
            "<synthetic-title>", "<script", "<link", "<img", "fetch(", "@import", "url(");
  }

  private static SessionTiming timing(double wallSeconds, String precision) {
    return new SessionTiming(
        wallSeconds,
        precision,
        null,
        "unknown",
        "",
        null,
        "unknown",
        "",
        null,
        "unknown",
        null,
        "unknown",
        0,
        0,
        0);
  }

  private static String render(TokenProvenance provenance, SessionTiming timing) {
    Map<String, Object> metrics = new LinkedHashMap<>();
    metrics.put("total_tokens", 300L);
    metrics.put("fresh_input_tokens", 200L);
    metrics.put("output_tokens", 100L);
    metrics.put("cache_read_tokens", 0L);
    metrics.put("cache_write_tokens", 0L);
    metrics.put("duration_seconds", 0.0);
    metrics.put("token_provenance", provenance);
    metrics.put("timing", timing);
    Map<String, Object> context = new LinkedHashMap<>();
    context.put("session", Map.of("title", "<synthetic-title>", "agent", "claude_code"));
    context.put("session_id", "synthetic-export");
    context.put("current_agent", "claude_code");
    context.put("session_metrics", metrics);
    context.put("payload_hidden", true);
    context.put("has_rounds", false);
    context.put("round_count", 0);
    return new PebbleEnvironment().render("export-session.html", context);
  }

  private static String metric(String html, String key) {
    var matcher =
        Pattern.compile(
                "data-export-metric=\""
                    + Pattern.quote(key)
                    + "\"[^>]*>\\s*<span class=\"sd-metric__value\">(.*?)</span>",
                Pattern.DOTALL)
            .matcher(html);
    assertThat(matcher.find()).as("export metric %s", key).isTrue();
    return matcher.group(1).replaceAll("\\s+", " ").trim();
  }
}
