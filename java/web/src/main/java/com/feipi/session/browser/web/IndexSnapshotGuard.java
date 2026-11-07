package com.feipi.session.browser.web;

import com.feipi.session.browser.web.api.ApiResponses.ApiErrorResponse;
import io.javalin.http.Handler;
import java.util.Objects;
import java.util.function.Supplier;

/** 在 JSON handler 返回、响应提交之前验证单次请求的索引发布代号。 */
public final class IndexSnapshotGuard {
  /** 客户端批次和服务端响应共用的索引发布代号头。 */
  public static final String HEADER = "X-Session-Index-Generation";

  /** 非流式个人页面传给模板的请求内发布代号。 */
  public static final String PAGE_GENERATION = "index_generation";

  private final Supplier<String> generation;

  /**
   * 创建当前个人索引的快照守卫。
   *
   * @param generation 非缓存的已发布代号读取器
   */
  public IndexSnapshotGuard(Supplier<String> generation) {
    this.generation = Objects.requireNonNull(generation, "generation 不得为 null");
  }

  /**
   * 包装仅设置 JSON 结果、不直接写响应流的 handler。
   *
   * @param handler 原始 JSON 查询处理器
   * @return 在响应提交前完成同代验证的处理器
   */
  public Handler wrap(Handler handler) {
    return context -> {
      String before = generation.get();
      String expected = context.header(HEADER);
      context.header("Cache-Control", "no-store");
      if (expected != null && !expected.equals(before)) {
        context
            .status(409)
            .json(new ApiErrorResponse("index_generation_changed", "索引已更新，请重试整个查询批次"));
        return;
      }
      handler.handle(context);
      if (!before.equals(generation.get())) {
        context
            .status(409)
            .json(new ApiErrorResponse("index_generation_changed", "索引已更新，请重试整个查询批次"));
        return;
      }
      context.header(HEADER, before);
    };
  }

  /**
   * 在完整个人页面渲染前后验证发布代；换代时丢弃尚未提交的业务 HTML。
   *
   * @param handler 仅设置完整 HTML 结果、不写响应流的页面处理器
   * @return 同代页面或明确可重试的无业务数据错误页
   */
  public Handler wrapPage(Handler handler) {
    return context -> {
      String before = generation.get();
      String expected = context.header(HEADER);
      SecurityHeaders.apply(context);
      if (expected == null || expected.equals(before)) {
        context.attribute(PAGE_GENERATION, before);
        handler.handle(context);
        if (before.equals(generation.get())) {
          context.header(HEADER, before);
          return;
        }
      }
      context
          .status(409)
          .html(
              "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                  + "<title>索引已更新</title></head><body><main role=\"alert\">"
                  + "<h1>索引已更新，请重试</h1><p>index_generation_changed</p>"
                  + "<a href=\"\">Reload / 重试当前页面</a></main></body></html>");
    };
  }
}
