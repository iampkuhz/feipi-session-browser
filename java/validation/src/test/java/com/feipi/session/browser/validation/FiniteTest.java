package com.feipi.session.browser.validation;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** {@link Finite} 单元测试。 */
class FiniteTest {

  private record Sample(@Finite Double value) {}

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  @Test
  void nullShouldBeValid() {
    assertThat(validate(new Sample(null))).isEmpty();
  }

  @Test
  void zeroShouldBeValid() {
    assertThat(validate(new Sample(0.0))).isEmpty();
  }

  @Test
  void normalValueShouldBeValid() {
    assertThat(validate(new Sample(123.45))).isEmpty();
  }

  @Test
  void nanShouldBeInvalid() {
    assertThat(validate(new Sample(Double.NaN))).isNotEmpty();
  }

  @Test
  void positiveInfinityShouldBeInvalid() {
    assertThat(validate(new Sample(Double.POSITIVE_INFINITY))).isNotEmpty();
  }

  @Test
  void negativeInfinityShouldBeInvalid() {
    assertThat(validate(new Sample(Double.NEGATIVE_INFINITY))).isNotEmpty();
  }

  @Test
  void floatNullShouldBeValid() {
    FloatRecord sample = new FloatRecord(null);
    Set<ConstraintViolation<FloatRecord>> violations = VALIDATOR.validate(sample);
    assertThat(violations).isEmpty();
  }

  @Test
  void floatNanShouldBeInvalid() {
    FloatRecord sample = new FloatRecord(Float.NaN);
    Set<ConstraintViolation<FloatRecord>> violations = VALIDATOR.validate(sample);
    assertThat(violations).isNotEmpty();
  }

  private record FloatRecord(@Finite Float value) {}

  private static Set<ConstraintViolation<Sample>> validate(Sample sample) {
    return VALIDATOR.validate(sample);
  }
}
