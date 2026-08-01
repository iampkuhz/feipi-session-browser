package com.feipi.session.browser.quality.gates.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** 违规 DTO 与稳定 JSON contract。 */
class QualityViolationTest {

  @Test
  void defensivelyCopiesAttributesAndSortsJsonKeys() {
    var attributes = new LinkedHashMap<String, String>();
    attributes.put("z", "last");
    attributes.put("a", "first");
    var violation = new QualityViolation("rule", "java/X.java", 3, "CODE", "message", attributes);
    attributes.clear();

    var json =
        QualitySummary.json(
            1, List.of(new QualitySummary.RuleExecution("rule", 1, List.of(violation))));

    assertThat(violation.attributes()).containsEntry("z", "last");
    assertThat(json).contains("\"attributes\":{\"a\":\"first\",\"z\":\"last\"}");
  }

  @Test
  void rejectsInvalidRequiredFields() {
    assertThatThrownBy(() -> new QualityViolation("", "X.java", 1, "C", "m", Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new QualityViolation("r", "X.java", 0, "C", "m", Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void reportsCandidateStatusForEachRule() {
    var json =
        QualitySummary.json(
            1,
            List.of(
                new QualitySummary.RuleExecution("full-scan", 1, List.of()),
                new QualitySummary.RuleExecution("incremental", 0, List.of())));

    assertThat(json)
        .contains("\"status\":\"PASSED\"")
        .contains(
            "{\"rule\":\"full-scan\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"incremental\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0,\"advisoryCount\":0}");
  }

  @Test
  void preservesEachRuleStableDiagnosticOrder() {
    var first = new QualityViolation("rule", "z.html", 2, "FIRST", "first", Map.of());
    var second = new QualityViolation("rule", "a.js", 1, "SECOND", "second", Map.of());

    var json =
        QualitySummary.json(
            2, List.of(new QualitySummary.RuleExecution("rule", 2, List.of(first, second))));

    assertThat(json).containsSubsequence("z.html", "a.js");
  }

  @Test
  void advisoryDoesNotFailRuleAndUsesNeutralSummaryVocabulary() {
    var advisory =
        new QualityAdvisory(
            "rule", "web/page.css", 4, "COLOR_DEBT", "建议改用 token。", Map.of("z", "1"));

    var json =
        QualitySummary.json(
            1, List.of(new QualitySummary.RuleExecution("rule", 1, List.of(), List.of(advisory))));

    assertThat(json)
        .isEqualTo(
            "{\"status\":\"PASSED\",\"candidateCount\":1,\"rules\":["
                + "{\"rule\":\"rule\",\"status\":\"PASSED\",\"candidateCount\":1,"
                + "\"violationCount\":0,\"advisoryCount\":1}],\"violations\":[],"
                + "\"advisories\":[{\"rule\":\"rule\",\"path\":\"web/page.css\",\"line\":4,"
                + "\"code\":\"COLOR_DEBT\",\"message\":\"建议改用 token。\","
                + "\"attributes\":{\"z\":\"1\"}}]}\n")
        .doesNotContainIgnoringCase("warning")
        .doesNotContain("[WARN]");
  }

  @Test
  void rejectsAdvisoryWithWrongRuleOrWithoutCandidate() {
    var advisory = new QualityAdvisory("other", "web/page.css", 1, "CODE", "建议处理。", Map.of());

    assertThatThrownBy(
            () -> new QualitySummary.RuleExecution("rule", 1, List.of(), List.of(advisory)))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> new QualitySummary.RuleExecution("other", 0, List.of(), List.of(advisory)))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
