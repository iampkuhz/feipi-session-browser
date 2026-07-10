package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * 会话详情查询请求。
 *
 * <p>封装按主键查找会话详情所需的全部参数，不含 HTTP 上下文。 下游 assembler 信任已验证的字段，不重复解析。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 不得为 null 或空字符串。
 *   <li>{@code visibility} 不得为 null，默认 {@link PayloadVisibility#STANDARD}。
 * </ul>
 *
 * @param sessionKey 会话主键，格式 {@code agent:session_id}
 * @param visibility payload 可见性策略，控制敏感字段是否展开
 */
public record SessionDetailRequest(
    /* 会话主键，格式 {@code agent:session_id}。 */
    @NotBlank String sessionKey,

    /* payload 可见性策略，控制敏感字段是否展开。 */
    @NotNull PayloadVisibility visibility) {

  /**
   * 紧凑构造器，验证请求不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 sessionKey 为空字符串时
   */
  public SessionDetailRequest {
    try {
      ValidationSupport.validateCanonicalConstructor(
          SessionDetailRequest.class, sessionKey, visibility);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 使用标准可见性创建请求。
   *
   * @param sessionKey 会话主键
   * @return 标准可见性的详情请求
   */
  public static SessionDetailRequest standard(String sessionKey) {
    return new SessionDetailRequest(sessionKey, PayloadVisibility.STANDARD);
  }

  /**
   * 使用完整可见性创建请求，展开敏感字段。
   *
   * @param sessionKey 会话主键
   * @return 完整可见性的详情请求
   */
  public static SessionDetailRequest full(String sessionKey) {
    return new SessionDetailRequest(sessionKey, PayloadVisibility.FULL);
  }

  /**
   * 将 Jakarta 校验违规翻译为向后兼容的异常类型。
   *
   * @param e 原始校验违规异常
   */
  private static void translateValidation(ConstraintViolationException e) {
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
    }
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotBlank.class) {
        if (v.getInvalidValue() == null) {
          throw new NullPointerException(field + " 不得为 null");
        }
        throw new IllegalArgumentException(field + " 不得为空");
      }
    }
    throw e;
  }
}
