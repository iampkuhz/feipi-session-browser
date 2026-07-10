package com.feipi.session.browser.validation;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.math.BigDecimal;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** {@link Ratio} 单元测试。 */
class RatioTest {

  private record DoubleSample(@Ratio Double value) {}

  private record BigDecimalSample(@Ratio BigDecimal value) {}

  private record FloatSample(@Ratio Float value) {}

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  @Test
  void nullDoubleShouldBeValid() {
    assertThat(VALIDATOR.validate(new DoubleSample(null))).isEmpty();
  }

  @Test
  void zeroShouldBeValid() {
    assertThat(VALIDATOR.validate(new DoubleSample(0.0))).isEmpty();
  }

  @Test
  void halfShouldBeValid() {
    assertThat(VALIDATOR.validate(new DoubleSample(0.5))).isEmpty();
  }

  @Test
  void oneShouldBeValid() {
    assertThat(VALIDATOR.validate(new DoubleSample(1.0))).isEmpty();
  }

  @Test
  void slightlyBelowZeroShouldBeInvalid() {
    assertThat(VALIDATOR.validate(new DoubleSample(-0.01))).isNotEmpty();
  }

  @Test
  void aboveOneShouldBeValid() {
    assertThat(VALIDATOR.validate(new DoubleSample(1.01))).isEmpty();
  }

  @Test
  void nanShouldBeInvalid() {
    assertThat(VALIDATOR.validate(new DoubleSample(Double.NaN))).isNotEmpty();
  }

  @Test
  void positiveInfinityShouldBeInvalid() {
    assertThat(VALIDATOR.validate(new DoubleSample(Double.POSITIVE_INFINITY))).isNotEmpty();
  }

  @Test
  void bigDecimalNullShouldBeValid() {
    assertThat(VALIDATOR.validate(new BigDecimalSample(null))).isEmpty();
  }

  @Test
  void bigDecimalZeroShouldBeValid() {
    assertThat(VALIDATOR.validate(new BigDecimalSample(BigDecimal.ZERO))).isEmpty();
  }

  @Test
  void bigDecimalOneShouldBeValid() {
    assertThat(VALIDATOR.validate(new BigDecimalSample(BigDecimal.ONE))).isEmpty();
  }

  @Test
  void bigDecimalAboveOneShouldBeValid() {
    assertThat(VALIDATOR.validate(new BigDecimalSample(new BigDecimal("1.01")))).isEmpty();
  }

  @Test
  void bigDecimalBelowZeroShouldBeInvalid() {
    assertThat(VALIDATOR.validate(new BigDecimalSample(new BigDecimal("-0.01")))).isNotEmpty();
  }

  @Test
  void floatNullShouldBeValid() {
    assertThat(VALIDATOR.validate(new FloatSample(null))).isEmpty();
  }

  @Test
  void floatHalfShouldBeValid() {
    assertThat(VALIDATOR.validate(new FloatSample(0.5f))).isEmpty();
  }

  @Test
  void floatNanShouldBeInvalid() {
    Set<ConstraintViolation<FloatSample>> violations =
        VALIDATOR.validate(new FloatSample(Float.NaN));
    assertThat(violations).isNotEmpty();
  }

  @Test
  void floatInfinityShouldBeInvalid() {
    Set<ConstraintViolation<FloatSample>> violations =
        VALIDATOR.validate(new FloatSample(Float.POSITIVE_INFINITY));
    assertThat(violations).isNotEmpty();
  }
}
