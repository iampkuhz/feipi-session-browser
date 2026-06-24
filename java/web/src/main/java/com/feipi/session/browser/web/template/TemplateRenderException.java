package com.feipi.session.browser.web.template;

/**
 * 模板加载或渲染失败时抛出的未检查异常。
 *
 * <p>包装 Pebble 引擎的 {@link java.io.IOException}， 使调用方不需要在路由处理中声明受检异常。
 */
public class TemplateRenderException extends RuntimeException {

  private static final long serialVersionUID = 1L;

  /**
   * 创建模板渲染异常。
   *
   * @param message 错误描述
   * @param cause 底层原因
   */
  public TemplateRenderException(String message, Throwable cause) {
    super(message, cause);
  }
}
