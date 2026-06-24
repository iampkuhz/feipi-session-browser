package com.feipi.session.browser.web.model;

/**
 * 已验证的安全 HTML 片段包装器。
 *
 * <p>模板引擎默认对所有输出进行 HTML 转义；只有经过显式构造的 {@code SafeHtml} 才会作为原始 HTML 渲染。
 * 构造函数不可从外部访问，外部代码必须通过以下受控入口创建实例：
 *
 * <ul>
 *   <li>{@link #escaped(String)} — 对任意字符串进行 HTML 转义后包装
 *   <li>{@link #trusted(String)} — 标记已通过安全审查的 HTML（仅限 presentation 内部使用）
 * </ul>
 *
 * <p>校验放置：构造器在 presentation 边界执行转义，下游模板信任 {@code SafeHtml} 的值不变量。
 */
public sealed interface SafeHtml permits SafeHtmlImpl {

  /** 空的安全片段常量，用于空值默认返回。 */
  SafeHtml EMPTY = new SafeHtmlImpl("");

  /**
   * 返回包装的 HTML 字符串。
   *
   * @return 已转义或已审查的 HTML 字符串，永不为 null
   */
  String value();

  /**
   * 对任意字符串进行 HTML 转义后创建安全实例。
   *
   * <p>转义 {@code <}、{@code >}、{@code &}、{@code "}、{@code '} 为对应 HTML 实体。 适用于包装不可信输入（如用户提交内容、JSON
   * 文本）。
   *
   * @param raw 原始字符串，null 或空时返回 {@link #EMPTY}
   * @return 转义后的安全 HTML 实例
   */
  static SafeHtml escaped(String raw) {
    if (raw == null || raw.isEmpty()) {
      return EMPTY;
    }
    StringBuilder sb = new StringBuilder(raw.length() + 16);
    for (int i = 0; i < raw.length(); i++) {
      char c = raw.charAt(i);
      switch (c) {
        case '&' -> sb.append("&amp;");
        case '<' -> sb.append("&lt;");
        case '>' -> sb.append("&gt;");
        case '"' -> sb.append("&quot;");
        case '\'' -> sb.append("&#39;");
        default -> sb.append(c);
      }
    }
    return new SafeHtmlImpl(sb.toString());
  }

  /**
   * 标记已通过安全审查的 HTML 为可信实例。
   *
   * <p>仅限 presentation 内部使用，调用方必须确保输入 HTML 已经过充分净化（如来自安全 Markdown 渲染器）。 不得用于包装任意用户输入。
   *
   * @param html 已审查的 HTML 字符串，null 或空时返回 {@link #EMPTY}
   * @return 可信安全 HTML 实例
   */
  static SafeHtml trusted(String html) {
    if (html == null || html.isEmpty()) {
      return EMPTY;
    }
    return new SafeHtmlImpl(html);
  }

  /**
   * 将当前实例与另一个安全 HTML 拼接。
   *
   * @param other 另一个安全 HTML 片段
   * @return 拼接后的新实例
   */
  default SafeHtml append(SafeHtml other) {
    return new SafeHtmlImpl(this.value() + other.value());
  }

  /**
   * 使用指定 CSS 类名包装为 {@code <div>} 容器。
   *
   * <p>类名经过 HTML 转义，防止属性注入。
   *
   * @param className CSS 类名
   * @return 包装后的安全 HTML 实例
   */
  default SafeHtml wrapInDiv(String className) {
    String safeClass = escapeAttribute(className);
    return new SafeHtmlImpl("<div class=\"" + safeClass + "\">" + this.value() + "</div>");
  }

  /** 对属性值进行 HTML 转义。 */
  private static String escapeAttribute(String raw) {
    if (raw == null || raw.isEmpty()) {
      return "";
    }
    return raw.replace("&", "&amp;")
        .replace("\"", "&quot;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;");
  }
}
