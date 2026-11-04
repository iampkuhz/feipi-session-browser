package com.feipi.session.browser.index.api.imports;

import java.io.IOException;
import java.util.Objects;

/** 面向边界的安全导入错误；消息不得带原始正文、凭据或临时路径。 */
public final class SessionImportException extends IOException {

  private static final long serialVersionUID = 1L;
  private final String code;

  /**
   * 创建安全错误。
   *
   * @param code 稳定机器错误码
   * @param message 不含输入内容的可显示说明
   */
  public SessionImportException(String code, String message) {
    super(Objects.requireNonNull(message, "message"));
    this.code = Objects.requireNonNull(code, "code");
  }

  /** 返回稳定机器错误码。 */
  public String code() {
    return code;
  }
}
