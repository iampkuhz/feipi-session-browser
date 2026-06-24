package com.feipi.session.browser.web.model;

import java.util.Objects;

/**
 * {@link SafeHtml} 的包级私有实现。
 *
 * <p>外部代码无法直接实例化此类，必须通过 {@link SafeHtml#escaped(String)} 或 {@link SafeHtml#trusted(String)} 创建实例。
 * 这确保了任意字符串不能绕过转义直接成为安全 HTML。
 */
final class SafeHtmlImpl implements SafeHtml {

  private final String val;

  /**
   * 包级私有构造器，只接受已经过验证或转义的 HTML 字符串。
   *
   * @param value 已验证的 HTML 字符串，不得为 null
   */
  SafeHtmlImpl(String value) {
    this.val = Objects.requireNonNull(value, "SafeHtml value 不得为 null");
  }

  @Override
  public String value() {
    return val;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) {
      return true;
    }
    if (!(obj instanceof SafeHtml other)) {
      return false;
    }
    return val.equals(other.value());
  }

  @Override
  public int hashCode() {
    return val.hashCode();
  }

  @Override
  public String toString() {
    return "SafeHtml[" + val + "]";
  }
}
