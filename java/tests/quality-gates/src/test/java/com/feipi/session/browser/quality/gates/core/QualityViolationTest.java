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

    var json = QualitySummary.json("FAILED", 1, List.of("rule"), List.of(violation));

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
}
