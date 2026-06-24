package com.feipi.session.browser.web.template;

import com.feipi.session.browser.web.model.SafeHtml;
import org.commonmark.node.Node;
import org.commonmark.parser.Parser;
import org.commonmark.renderer.html.HtmlRenderer;

/**
 * 安全 Markdown 渲染器。
 *
 * <p>使用 CommonMark 解析 Markdown 为 HTML。通过禁用原始 HTML 块和行内 HTML， 防止 XSS 攻击向量（如 {@code <script>}、 {@code
 * <iframe>}、事件处理器属性）。
 *
 * <p>渲染结果经过安全审查，可通过 {@link SafeHtml#trusted(String)} 包装后在模板中直接输出。
 *
 * <p>校验放置：Markdown 源文本在 presentation 边界统一净化，下游模板信任 {@link SafeHtml} 的值不变量。
 */
public final class SafeMarkdownRenderer {

  private final Parser parser;
  private final HtmlRenderer renderer;

  /** 创建安全 Markdown 渲染器，禁用原始 HTML。 */
  public SafeMarkdownRenderer() {
    this.parser = Parser.builder().build();
    this.renderer =
        HtmlRenderer.builder()
            // 转义 HTML 块级标签（如 <script>、<div>）为文本
            .escapeHtml(true)
            .build();
  }

  /**
   * 将 Markdown 文本渲染为安全 HTML。
   *
   * <p>原始 HTML 标签会被转义为文本实体，防止 XSS。null 或空输入返回空安全 HTML。
   *
   * @param markdown Markdown 源文本
   * @return 安全 HTML 包装结果，可直接在模板中使用
   */
  public SafeHtml render(String markdown) {
    if (markdown == null || markdown.isEmpty()) {
      return SafeHtml.EMPTY;
    }
    Node document = parser.parse(markdown);
    String html = renderer.render(document);
    return SafeHtml.trusted(html);
  }
}
