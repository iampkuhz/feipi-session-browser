package com.feipi.session.browser.web.template;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.feipi.session.browser.web.model.SafeHtml;
import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import org.commonmark.ext.gfm.tables.TablesExtension;
import org.commonmark.node.Code;
import org.commonmark.node.Heading;
import org.commonmark.node.HtmlInline;
import org.commonmark.node.Image;
import org.commonmark.node.Link;
import org.commonmark.node.Node;
import org.commonmark.node.Paragraph;
import org.commonmark.node.Text;
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

  private static final SafeMarkdownRenderer SHARED = new SafeMarkdownRenderer();
  private static final JsonMapper STRUCTURED =
      JsonMapper.builder().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).build();
  private static final Set<String> LOOPBACK = Set.of("localhost", "127.0.0.1", "[::1]");
  private static final Pattern SESSION_PATH =
      Pattern.compile("/sessions/(claude_code|codex|qoder)/[A-Za-z0-9_-]{1,128}");
  private static final Pattern CODEX_THREAD_PATH =
      Pattern.compile("/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}");

  private static final Pattern LITERAL_PROJECT_OPENER =
      Pattern.compile(
          "\\A(\\s*# AGENTS\\.md instructions for [^\\r\\n]+\\R(?:[ \\t]*\\R)*[ \\t]*)"
              + "<INSTRUCTIONS>(?=[ \\t]*(?:\\R|\\z))");

  private final Parser parser;
  private final HtmlRenderer renderer;

  /** 创建安全 Markdown 渲染器，禁用原始 HTML。 */
  public SafeMarkdownRenderer() {
    var extensions = List.of(TablesExtension.create());
    this.parser = Parser.builder().extensions(extensions).build();
    this.renderer =
        HtmlRenderer.builder().extensions(extensions).escapeHtml(true).sanitizeUrls(true).build();
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
    sanitize(document);
    return SafeHtml.trusted(renderer.render(document));
  }

  /** 页面标题只展示首行的内联内容；保留原始标题供调用方明确查看。 */
  public static Title title(String source) {
    String first = source == null ? "" : source.strip().lines().findFirst().orElse("");
    if (first.isEmpty() || first.startsWith("{\"") || first.startsWith("[{\"")) {
      return new Title("", "");
    }
    Node document = SHARED.parser.parse(first);
    Node line = document.getFirstChild();
    if (!(line instanceof Paragraph || line instanceof Heading)) {
      return new Title("", "");
    }
    sanitize(line);
    StringBuilder label = new StringBuilder();
    StringBuilder html = new StringBuilder();
    appendLabel(line, label);
    for (Node node = line.getFirstChild(); node != null; node = node.getNext()) {
      html.append(SHARED.renderer.render(node));
    }
    return new Title(label.toString(), html.toString());
  }

  /**
   * 同一标题的两种安全表示。
   *
   * @param text 表格和标签使用的纯文本
   * @param html 详情页使用的安全内联内容
   */
  public record Title(String text, String html) {}

  /** 返回结构化 Markdown；简单文本及 JSON 由原文样式展示。 */
  public static String readingHtml(String text) {
    if (text.isBlank() || isJson(text)) return "";
    // 保留说明标签字面值，不让 CommonMark 的 HTML 块吞掉后续围栏和正文。
    String markdown = LITERAL_PROJECT_OPENER.matcher(text).replaceFirst("$1&lt;INSTRUCTIONS>");
    Node document = SHARED.parser.parse(markdown);
    if (document.getFirstChild() instanceof Paragraph paragraph
        && paragraph.getNext() == null
        && isPlainParagraph(paragraph)) return "";
    sanitize(document);
    return SHARED.renderer.render(document);
  }

  private static boolean isPlainParagraph(Node node) {
    for (Node child = node.getFirstChild(); child != null; child = child.getNext()) {
      if (!(child instanceof Text
          || child instanceof HtmlInline
          || child instanceof org.commonmark.node.SoftLineBreak
          || child instanceof org.commonmark.node.HardLineBreak)) return false;
    }
    return true;
  }

  private static boolean isJson(String text) {
    String stripped = text.stripLeading();
    if (!stripped.startsWith("{") && !stripped.startsWith("[")) return false;
    try {
      return STRUCTURED.readTree(stripped).isContainerNode();
    } catch (JsonProcessingException invalid) {
      return false;
    }
  }

  private static void sanitize(Node parent) {
    for (Node child = parent.getFirstChild(); child != null; ) {
      Node next = child.getNext();
      if (child instanceof Image) {
        replaceWithLabel(child, false);
      } else if (child instanceof Link link) {
        String destination = link.getDestination();
        boolean skill = destination.toLowerCase(Locale.ROOT).endsWith("/skill.md");
        String safe = skill ? "" : safeDestination(destination);
        if (safe.isEmpty()) {
          replaceWithLabel(link, skill);
        } else {
          link.setDestination(safe);
          sanitize(link);
        }
      } else {
        sanitize(child);
      }
      child = next;
    }
  }

  private static void replaceWithLabel(Node node, boolean code) {
    StringBuilder label = new StringBuilder();
    appendLabel(node, label);
    if (code) {
      Code reference = new Code();
      reference.setLiteral(label.toString());
      node.insertBefore(reference);
    } else {
      node.insertBefore(new Text(label.toString()));
    }
    node.unlink();
  }

  private static void appendLabel(Node node, StringBuilder out) {
    if (node instanceof Text text) out.append(text.getLiteral());
    if (node instanceof Code code) out.append(code.getLiteral());
    if (node instanceof HtmlInline html) out.append(html.getLiteral());
    for (Node child = node.getFirstChild(); child != null; child = child.getNext()) {
      appendLabel(child, out);
    }
  }

  private static String safeDestination(String raw) {
    try {
      URI uri = URI.create(raw);
      String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
      String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
      String path = uri.getRawPath() == null ? "" : uri.getRawPath();
      boolean web = "http".equals(scheme) || "https".equals(scheme);
      if (uri.getRawUserInfo() != null) return "";
      if (SESSION_PATH.matcher(path).matches()
          && ((scheme.isEmpty() && uri.getRawAuthority() == null)
              || (web && LOOPBACK.contains(host)))) {
        return path;
      }
      if ("codex".equals(scheme)
          && "threads".equals(host)
          && CODEX_THREAD_PATH.matcher(path).matches()) {
        return "/sessions/codex" + path;
      }
      return web && !host.isEmpty() && !LOOPBACK.contains(host) ? raw : "";
    } catch (IllegalArgumentException invalid) {
      return "";
    }
  }
}
