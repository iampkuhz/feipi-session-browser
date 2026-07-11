package com.feipi.session.browser.quality.gates.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** {@link QualityViolation} 防御性构造器测试。 */
class QualityViolationTest {

  @Test
  void constructsSuccessfully() {
    var v = new QualityViolation(Path.of("X.java"), 10, "CODE", "msg", Map.of("k", "v"));
    assertThat(v.path()).isEqualTo(Path.of("X.java"));
    assertThat(v.line()).isEqualTo(10);
    assertThat(v.code()).isEqualTo("CODE");
    assertThat(v.message()).isEqualTo("msg");
    assertThat(v.attributes()).containsEntry("k", "v");
  }

  @Test
  void nullPathThrows() {
    assertThatThrownBy(() -> new QualityViolation(null, 1, "C", "m", null))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  void zeroLineThrows() {
    assertThatThrownBy(() -> new QualityViolation(Path.of("X"), 0, "C", "m", null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void blankCodeThrows() {
    assertThatThrownBy(() -> new QualityViolation(Path.of("X"), 1, "", "m", null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void blankMessageThrows() {
    assertThatThrownBy(() -> new QualityViolation(Path.of("X"), 1, "C", "  ", null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void nullAttributesBecomesEmpty() {
    var v = new QualityViolation(Path.of("X"), 1, "C", "m", null);
    assertThat(v.attributes()).isEmpty();
  }

  @Test
  void attributesAreImmutable() {
    var v = new QualityViolation(Path.of("X"), 1, "C", "m", Map.of("k", "v"));
    assertThatThrownBy(() -> v.attributes().put("x", "y"))
        .isInstanceOf(UnsupportedOperationException.class);
  }
}
