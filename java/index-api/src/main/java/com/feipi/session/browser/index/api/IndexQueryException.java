package com.feipi.session.browser.index.api;

/** 通过抽象端口查询索引失败时使用的非受检异常。 */
public final class IndexQueryException extends RuntimeException {
  private static final long serialVersionUID = 1L;

  /** 使用错误消息和根因创建异常。 */
  public IndexQueryException(String message, Throwable cause) {
    super(message, cause);
  }
}
