package com.feipi.session.browser.web.model;

import com.feipi.session.browser.query.api.PayloadVisibility;
import io.javalin.http.Context;

/** payload visibility 查询参数解析器。 */
public final class PayloadVisibilityQuery {

  private PayloadVisibilityQuery() {}

  /** 解析 payload visibility 查询参数；默认返回 STANDARD。 */
  public static PayloadVisibility parse(Context ctx) {
    return "full".equalsIgnoreCase(ctx.queryParam("visibility"))
        ? PayloadVisibility.FULL
        : PayloadVisibility.STANDARD;
  }
}
