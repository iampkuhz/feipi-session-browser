package com.feipi.session.browser.web.template;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.web.model.SafeHtml;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link SafeMarkdownRenderer} 安全测试。
 *
 * <p>验证 Markdown 渲染禁用原始 HTML（XSS 防护）和基本格式化正确。
 */
@DisplayName("安全 Markdown 渲染测试")
class SafeMarkdownRendererTest {

  private final SafeMarkdownRenderer renderer = new SafeMarkdownRenderer();

  @Nested
  @DisplayName("XSS 防护")
  class XssProtection {

    @Test
    @DisplayName("script 标签被转义而非执行")
    void scriptTagEscaped() {
      SafeHtml result = renderer.render("<script>alert('xss')</script>");
      assertThat(result.value()).doesNotContain("<script>");
      assertThat(result.value()).contains("&lt;script&gt;");
    }

    @Test
    @DisplayName("iframe 标签被转义")
    void iframeTagEscaped() {
      SafeHtml result = renderer.render("<iframe src='evil.com'></iframe>");
      assertThat(result.value()).doesNotContain("<iframe");
    }

    @Test
    @DisplayName("HTML 事件处理器属性被转义为文本")
    void eventHandlerEscaped() {
      SafeHtml result = renderer.render("<img onerror='alert(1)' src=x>");
      // 标签本身被转义，< 变为 &lt;，因此不可能作为 HTML 标签解析
      assertThat(result.value()).doesNotContain("<img ");
      assertThat(result.value()).contains("&lt;img");
    }

    @Test
    @DisplayName("XSS corpus: 常见攻击向量的标签全部转义")
    void xssCorpusNeutralized() {
      String[] attackVectors = {
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(1)>",
        "<body onload=alert(1)>",
        "<a href='javascript:alert(1)'>click</a>",
        "`` `javascript:alert(1)` ``",
      };
      for (String vector : attackVectors) {
        SafeHtml result = renderer.render(vector);
        // 核心不变量：输出中不存在未转义的 < 标签（标签开头被转义为 &lt;）
        // 因此任何看似属性的文本都只是普通文本内容，不会被浏览器解析
        String html = result.value();
        assertThat(html)
            .as("标签应被转义: %s", vector)
            .doesNotContain("<script", "<iframe", "<img ", "<svg ", "<body ", "<a ");
      }
    }
  }

  @Nested
  @DisplayName("基本 Markdown 渲染")
  class BasicRendering {

    @Test
    @DisplayName("段落正常渲染为 <p> 标签")
    void paragraphRendered() {
      SafeHtml result = renderer.render("Hello world");
      assertThat(result.value()).contains("<p>Hello world</p>");
    }

    @Test
    @DisplayName("粗体正常渲染")
    void boldRendered() {
      SafeHtml result = renderer.render("**bold text**");
      assertThat(result.value()).contains("<strong>bold text</strong>");
    }

    @Test
    @DisplayName("链接正常渲染")
    void linkRendered() {
      SafeHtml result = renderer.render("[link](https://example.com)");
      assertThat(result.value()).contains("<a href=\"https://example.com\">link</a>");
    }

    @Test
    @DisplayName("代码块正常渲染")
    void codeBlockRendered() {
      SafeHtml result = renderer.render("```\ncode\n```");
      assertThat(result.value()).contains("<code>");
    }
  }

  @Nested
  @DisplayName("空值处理")
  class NullHandling {

    @Test
    @DisplayName("null 输入返回 EMPTY")
    void nullReturnsEmpty() {
      assertThat(renderer.render(null)).isSameAs(SafeHtml.EMPTY);
    }

    @Test
    @DisplayName("空字符串返回 EMPTY")
    void emptyReturnsEmpty() {
      assertThat(renderer.render("")).isSameAs(SafeHtml.EMPTY);
    }
  }
}
