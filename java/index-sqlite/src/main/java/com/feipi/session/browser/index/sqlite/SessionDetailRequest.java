package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.Objects;

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
public record SessionDetailRequest(String sessionKey, PayloadVisibility visibility) {

  /**
   * 紧凑构造器，验证请求不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 sessionKey 为空字符串时
   */
  public SessionDetailRequest {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    if (sessionKey.isEmpty()) {
      throw new IllegalArgumentException("sessionKey 不得为空字符串");
    }
    Objects.requireNonNull(visibility, "visibility 不得为 null");
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
}
