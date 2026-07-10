package com.feipi.session.browser.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.executable.ExecutableValidator;
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Jakarta Validation 统一入口。
 *
 * <p>record compact constructor 中不能用 {@code this} 校验 bean，因为 record field 尚未赋值。需要校验 canonical
 * constructor parameters。该类缓存 canonical constructor，避免各 record 重复反射解析。
 */
public final class ValidationSupport {

  private static final ValidatorFactory FACTORY = Validation.buildDefaultValidatorFactory();
  private static final Validator VALIDATOR = FACTORY.getValidator();
  private static final ExecutableValidator EXECUTABLE_VALIDATOR = VALIDATOR.forExecutables();

  private static final Map<Class<?>, Constructor<?>> CANONICAL_CONSTRUCTORS =
      new ConcurrentHashMap<>();

  private ValidationSupport() {}

  /**
   * 校验完整 bean 实例。
   *
   * @param bean 待校验实例
   * @param <T> bean 类型
   * @throws ConstraintViolationException 当存在约束违规时
   */
  public static <T> void validateBean(T bean) {
    Set<ConstraintViolation<T>> violations = VALIDATOR.validate(bean);
    if (!violations.isEmpty()) {
      throw new ConstraintViolationException(violations);
    }
  }

  /**
   * 校验 record canonical constructor 参数。
   *
   * <p>必须在 compact constructor 内调用，并传入与 record component 顺序完全一致的参数。注意：compact constructor 里不能用
   * {@code this} 校验 bean，因为 record field 尚未赋值。
   *
   * @param recordType record 类型
   * @param args canonical constructor 参数值，顺序必须与 record component 一致
   * @param <T> record 类型
   * @throws IllegalArgumentException 当 recordType 不是 record 时
   * @throws ConstraintViolationException 当存在约束违规时
   */
  public static <T extends Record> void validateCanonicalConstructor(
      Class<T> recordType, Object... args) {
    Constructor<T> constructor = canonicalConstructor(recordType);
    Set<ConstraintViolation<T>> violations =
        EXECUTABLE_VALIDATOR.validateConstructorParameters(constructor, args);
    if (!violations.isEmpty()) {
      throw new ConstraintViolationException(violations);
    }
  }

  @SuppressWarnings("unchecked")
  private static <T extends Record> Constructor<T> canonicalConstructor(Class<T> recordType) {
    if (!recordType.isRecord()) {
      throw new IllegalArgumentException("类型不是 record: " + recordType.getName());
    }
    return (Constructor<T>)
        CANONICAL_CONSTRUCTORS.computeIfAbsent(
            recordType,
            type -> {
              try {
                Class<?>[] parameterTypes =
                    Arrays.stream(type.getRecordComponents())
                        .map(RecordComponent::getType)
                        .toArray(Class<?>[]::new);
                Constructor<?> constructor = type.getDeclaredConstructor(parameterTypes);
                constructor.setAccessible(true);
                return constructor;
              } catch (ReflectiveOperationException ex) {
                throw new IllegalArgumentException(
                    "无法解析 record canonical constructor: " + type.getName(), ex);
              }
            });
  }
}
