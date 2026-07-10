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
import java.math.BigDecimal;

/**
 * 校验比值为非负有限数；支持 Double、Float、BigDecimal 等 Number 子类型。null 表示无数据，视为 valid。NaN 和 Infinity 视为 invalid。
 */
@Documented
@Constraint(validatedBy = Ratio.NumberValidator.class)
@Target({FIELD, METHOD, PARAMETER, RECORD_COMPONENT, TYPE_USE, ANNOTATION_TYPE})
@Retention(RUNTIME)
public @interface Ratio {

  /** 默认违规消息 key。 */
  String message() default "{com.feipi.session.browser.validation.Ratio.message}";

  /** 约束分组。 */
  Class<?>[] groups() default {};

  /** 约束违规时的自定义负载类型，通常不需要指定。 */
  Class<? extends Payload>[] payload() default {};

  /** 数值校验器，空值视为合法输入，非数字或无穷大视为非法输入，有效范围为非负有限数。 */
  final class NumberValidator implements ConstraintValidator<Ratio, Number> {
    @Override
    public boolean isValid(Number value, ConstraintValidatorContext context) {
      if (value == null) {
        return true;
      }
      if (value instanceof BigDecimal decimal) {
        return decimal.compareTo(BigDecimal.ZERO) >= 0;
      }
      double numeric = value.doubleValue();
      return Double.isFinite(numeric) && numeric >= 0.0d;
    }
  }
}
