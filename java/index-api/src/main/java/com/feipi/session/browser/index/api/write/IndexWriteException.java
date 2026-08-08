package com.feipi.session.browser.index.api.write;

/** 索引写侧端口操作失败时抛出的运行时异常。 */
public final class IndexWriteException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  /**
   * 使用写索引失败信息和原始原因创建异常，不额外校验或转换参数。
   *
   * @param message 面向调用方的失败信息，可为 {@code null}
   * @param cause 导致写入失败的原始异常，可为 {@code null}
   */
  public IndexWriteException(String message, Throwable cause) {
    super(message, cause);
  }

  /**
   * 仅使用写索引失败信息创建异常，不额外校验参数。
   *
   * @param message 面向调用方的失败信息，可为 {@code null}
   */
  public IndexWriteException(String message) {
    super(message);
  }
}
