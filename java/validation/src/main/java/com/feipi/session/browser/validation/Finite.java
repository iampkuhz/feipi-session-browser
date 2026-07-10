package com.feipi.session.browser.validation;

import static java.lang.annotation.ElementType.ANNOTATION_TYPE;
import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.RECORD_COMPONENT;
import static java.lang.annotation.ElementType.TYPE_USE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

/** 校验浮点数为有限值（非 NaN、非 Infinity）；null 表示未提供，视为 valid。 */
@Documented
@Constraint(validatedBy = {Finite.DoubleValidator.class, Finite.FloatValidator.class})
@Target({FIELD, METHOD, PARAMETER, RECORD_COMPONENT, TYPE_USE, ANNOTATION_TYPE})
@Retention(RUNTIME)
public @interface Finite {

  /** 默认违规消息 key。 */
  String message() default "{com.feipi.session.browser.validation.Finite.message}";

  /** 约束分组。 */
  Class<?>[] groups() default {};

  /** 约束违规时的自定义负载类型，通常不需要指定。 */
  Class<? extends Payload>[] payload() default {};

  /** 双精度浮点校验器，空值视为合法输入，非数字或无穷大视为非法输入。 */
  final class DoubleValidator implements ConstraintValidator<Finite, Double> {
    @Override
    public boolean isValid(Double value, ConstraintValidatorContext context) {
      return value == null || Double.isFinite(value);
    }
  }

  /** 单精度浮点校验器，空值视为合法输入，非数字或无穷大视为非法输入。 */
  final class FloatValidator implements ConstraintValidator<Finite, Float> {
    @Override
    public boolean isValid(Float value, ConstraintValidatorContext context) {
      return value == null || Float.isFinite(value);
    }
  }
}
