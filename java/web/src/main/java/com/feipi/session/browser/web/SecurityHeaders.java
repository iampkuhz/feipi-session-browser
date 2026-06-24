package com.feipi.session.browser.web;

import io.javalin.http.Context;
import io.javalin.http.Header;

/**
 * HTTP 安全响应头配置。
 *
 * <p>作为 Javalin before-handler 注册，为所有响应添加安全相关的 HTTP 头：
 *
 * <ul>
 *   <li>{@code Content-Security-Policy} — 限制资源加载源，禁止内联脚本和外部域
 *   <li>{@code X-Frame-Options} — 禁止页面被嵌入 iframe，防止点击劫持
 *   <li>{@code X-Content-Type-Options} — 禁止浏览器 MIME 嗅探
 *   <li>{@code Cache-Control} — 禁止缓存本地会话数据
 *   <li>{@code X-XSS-Protection} — 旧版浏览器 XSS 过滤器（设为 0，避免 mXSS）
 *   <li>{@code Referrer-Policy} — 限制 Referer 头泄漏
 * </ul>
 *
 * <p>校验放置：安全头在 HTTP adapter 入口统一注入，下游 handler 不需要单独设置。
 */
public final class SecurityHeaders {

  /** CSP 策略：只允许同源资源，禁止内联脚本（使用 nonce 或 strict-dynamic 后续迭代）。 */
  static final String CSP_VALUE =
      "default-src 'self'; "
          + "script-src 'self' 'unsafe-inline'; "
          + "style-src 'self' 'unsafe-inline'; "
          + "img-src 'self' data:; "
          + "font-src 'self'; "
          + "connect-src 'self'; "
          + "frame-ancestors 'none'; "
          + "base-uri 'self'; "
          + "form-action 'self'";

  private static final String CACHE_CONTROL_VALUE =
      "no-store, no-cache, must-revalidate, max-age=0";

  private SecurityHeaders() {}

  /**
   * 为当前响应设置全部安全头。
   *
   * <p>设计为 Javalin {@code config.browsing.before} 处理器，在每个请求路由匹配前执行。
   *
   * @param ctx Javalin 请求上下文
   */
  public static void apply(Context ctx) {
    ctx.header(Header.CONTENT_SECURITY_POLICY, CSP_VALUE);
    ctx.header(Header.X_FRAME_OPTIONS, "DENY");
    ctx.header(Header.X_CONTENT_TYPE_OPTIONS, "nosniff");
    ctx.header(Header.CACHE_CONTROL, CACHE_CONTROL_VALUE);
    ctx.header("X-XSS-Protection", "0");
    ctx.header(Header.REFERRER_POLICY, "strict-origin-when-cross-origin");
  }
}
