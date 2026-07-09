package com.feipi.session.browser.index.api.write;

/** 索引写侧端口操作失败时抛出的运行时异常。 */
public final class IndexWriteException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  public IndexWriteException(String message, Throwable cause) {
    super(message, cause);
  }

  public IndexWriteException(String message) {
    super(message);
  }
}
