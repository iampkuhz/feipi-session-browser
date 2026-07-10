package com.feipi.session.browser.validation;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import org.junit.jupiter.api.Test;

/** {@link ValidationSupport} 单元测试。 */
class ValidationSupportTest {

  private record SampleRecord(
      @NotBlank String name, @PositiveOrZero long count, @Ratio Double ratio) {

    private SampleRecord {
      ValidationSupport.validateCanonicalConstructor(SampleRecord.class, name, count, ratio);
    }
  }

  @Test
  void validRecordShouldNotThrow() {
    assertThatCode(() -> new SampleRecord("test", 10L, 0.5)).doesNotThrowAnyException();
  }

  @Test
  void blankNameShouldThrow() {
    assertThatThrownBy(() -> new SampleRecord("  ", 10L, 0.5))
        .isInstanceOf(ConstraintViolationException.class)
        .satisfies(
            ex -> {
              ConstraintViolationException cve = (ConstraintViolationException) ex;
              assertThatViolationContainsAnnotation(cve, NotBlank.class);
            });
  }

  @Test
  void negativeCountShouldThrow() {
    assertThatThrownBy(() -> new SampleRecord("test", -1L, 0.5))
        .isInstanceOf(ConstraintViolationException.class)
        .satisfies(
            ex -> {
              ConstraintViolationException cve = (ConstraintViolationException) ex;
              assertThatViolationContainsAnnotation(cve, PositiveOrZero.class);
            });
  }

  @Test
  void ratioAboveOneShouldBeValid() {
    assertThatCode(() -> new SampleRecord("test", 10L, 1.01)).doesNotThrowAnyException();
  }

  @Test
  void nullRatioShouldBeValid() {
    assertThatCode(() -> new SampleRecord("test", 10L, null)).doesNotThrowAnyException();
  }

  @SuppressWarnings({"unchecked", "rawtypes"})
  @Test
  void nonRecordTypeShouldThrowIllegalArgument() {
    Class rawClass = String.class;
    assertThatThrownBy(() -> ValidationSupport.validateCanonicalConstructor(rawClass, "test"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("不是 record");
  }

  private static void assertThatViolationContainsAnnotation(
      ConstraintViolationException cve, Class<?> annotationType) {
    boolean found =
        cve.getConstraintViolations().stream()
            .map(ConstraintViolation::getConstraintDescriptor)
            .anyMatch(d -> annotationType.isAssignableFrom(d.getAnnotation().annotationType()));
    org.assertj.core.api.Assertions.assertThat(found)
        .as("应包含约束注解 %s", annotationType.getSimpleName())
        .isTrue();
  }
}
