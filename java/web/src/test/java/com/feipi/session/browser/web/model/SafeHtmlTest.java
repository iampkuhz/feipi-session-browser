package com.feipi.session.browser.web.model;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link SafeHtml} 安全 HTML 包装器测试。 */
@DisplayName("SafeHtml 安全 HTML 测试")
class SafeHtmlTest {

  @Nested
  @DisplayName("escaped 工厂方法")
  class EscapedFactory {

    @Test
    @DisplayName("转义 HTML 特殊字符")
    void escapesHtmlChars() {
      SafeHtml result = SafeHtml.escaped("<script>alert('xss')</script>");
      assertThat(result.value()).doesNotContain("<script>");
      assertThat(result.value()).contains("&lt;script&gt;");
      assertThat(result.value()).contains("&#39;");
    }

    @Test
    @DisplayName("转义引号")
    void escapesQuotes() {
      SafeHtml result = SafeHtml.escaped("a\"b&c");
      assertThat(result.value()).isEqualTo("a&quot;b&amp;c");
    }

    @Test
    @DisplayName("null 输入返回 EMPTY")
    void nullReturnsEmpty() {
      assertThat(SafeHtml.escaped(null)).isSameAs(SafeHtml.EMPTY);
    }

    @Test
    @DisplayName("空字符串返回 EMPTY")
    void emptyReturnsEmpty() {
      assertThat(SafeHtml.escaped("")).isSameAs(SafeHtml.EMPTY);
    }

    @Test
    @DisplayName("纯文本安全字符不改变")
    void plainTextUnchanged() {
      SafeHtml result = SafeHtml.escaped("hello world");
      assertThat(result.value()).isEqualTo("hello world");
    }
  }

  @Nested
  @DisplayName("trusted 工厂方法")
  class TrustedFactory {

    @Test
    @DisplayName("不转义内容")
    void doesNotEscape() {
      SafeHtml result = SafeHtml.trusted("<b>bold</b>");
      assertThat(result.value()).isEqualTo("<b>bold</b>");
    }

    @Test
    @DisplayName("null 输入返回 EMPTY")
    void nullReturnsEmpty() {
      assertThat(SafeHtml.trusted(null)).isSameAs(SafeHtml.EMPTY);
    }

    @Test
    @DisplayName("空字符串返回 EMPTY")
    void emptyReturnsEmpty() {
      assertThat(SafeHtml.trusted("")).isSameAs(SafeHtml.EMPTY);
    }
  }

  @Nested
  @DisplayName("构造器约束")
  class ConstructorConstraints {

    @Test
    @DisplayName("构造器不可从外部直接访问，只能通过工厂方法创建")
    void factoryMethodsOnly() {
      // escaped 方法存在且可调用
      SafeHtml escaped = SafeHtml.escaped("<b>");
      assertThat(escaped.value()).doesNotContain("<b>");

      // trusted 方法存在且可调用
      SafeHtml trusted = SafeHtml.trusted("<b>");
      assertThat(trusted.value()).isEqualTo("<b>");

      // SafeHtml 是 sealed interface，无法在包外通过 new 创建实例
      assertThat(SafeHtml.class.isSealed()).isTrue();
    }
  }

  @Nested
  @DisplayName("append 拼接")
  class Append {

    @Test
    @DisplayName("拼接两个安全片段")
    void appendsTwoFragments() {
      SafeHtml a = SafeHtml.trusted("<b>");
      SafeHtml b = SafeHtml.trusted("text</b>");
      SafeHtml result = a.append(b);
      assertThat(result.value()).isEqualTo("<b>text</b>");
    }
  }

  @Nested
  @DisplayName("wrapInDiv 包装")
  class WrapInDiv {

    @Test
    @DisplayName("使用 CSS 类名包装")
    void wrapsWithClassName() {
      SafeHtml content = SafeHtml.trusted("content");
      SafeHtml wrapped = content.wrapInDiv("my-class");
      assertThat(wrapped.value()).isEqualTo("<div class=\"my-class\">content</div>");
    }

    @Test
    @DisplayName("类名中的特殊字符被转义")
    void escapesClassName() {
      SafeHtml content = SafeHtml.trusted("x");
      SafeHtml wrapped = content.wrapInDiv("a\"b");
      assertThat(wrapped.value()).contains("&quot;");
    }
  }

  @Nested
  @DisplayName("对象语义")
  class ObjectSemantics {

    @Test
    @DisplayName("相等性基于 value")
    void equalityByValue() {
      SafeHtml a = SafeHtml.trusted("hello");
      SafeHtml b = SafeHtml.trusted("hello");
      assertThat(a).isEqualTo(b);
      assertThat(a.hashCode()).isEqualTo(b.hashCode());
    }

    @Test
    @DisplayName("toString 包含 value")
    void toStringContainsValue() {
      SafeHtml html = SafeHtml.trusted("test");
      assertThat(html.toString()).contains("test");
    }
  }
}
