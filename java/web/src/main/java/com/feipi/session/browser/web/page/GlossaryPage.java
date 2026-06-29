package com.feipi.session.browser.web.page;

import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Glossary 页面路由处理器。
 *
 * <p>处理 {@code GET /glossary} 请求，渲染 token 术语表页面。
 *
 * <p>页面内容为静态 HTML，无需动态数据加载。术语表说明 token 口径、派生指标、provider 字段映射和 badge 语义。
 */
public final class GlossaryPage {

  private static final Logger LOG = LoggerFactory.getLogger(GlossaryPage.class);

  private final PebbleEnvironment templates;

  /**
   * 创建 Glossary 页面处理器。
   *
   * @param templates Pebble 模板引擎
   */
  public GlossaryPage(PebbleEnvironment templates) {
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 glossary 页面请求。
   *
   * @param ctx Javalin 上下文
   */
  public void handle(Context ctx) {
    LOG.debug("渲染 glossary 页面");

    Map<String, Object> context = new HashMap<>();
    context.put("active_page", "glossary");

    String html = templates.render("glossary.html", context);
    ctx.html(html);
  }
}
