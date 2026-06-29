package com.feipi.session.browser.web.template;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.web.model.SafeHtml;
import io.pebbletemplates.pebble.PebbleEngine;
import io.pebbletemplates.pebble.loader.StringLoader;
import io.pebbletemplates.pebble.template.PebbleTemplate;
import java.io.IOException;
import java.io.StringWriter;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link PebbleEnvironment} 模板引擎配置与过滤器测试。
 *
 * <p>Acceptance contracts: ROUTE-API-004, UI-VISUAL-012
 */
@DisplayName("PebbleEnvironment 模板引擎测试")
class PebbleEnvironmentTest {

  @Nested
  @DisplayName("引擎创建")
  class EngineCreation {

    @Test
    @DisplayName("默认构造创建可用引擎")
    void defaultConstructorCreatesEngine() {
      PebbleEnvironment env = new PebbleEnvironment();
      assertThat(env.engine()).isNotNull();
    }

    @Test
    @DisplayName("自定义模板目录创建引擎")
    void customDirectoryCreatesEngine() {
      PebbleEnvironment env = new PebbleEnvironment("custom-templates");
      assertThat(env.engine()).isNotNull();
    }

    @Test
    @DisplayName("null 模板目录抛出异常")
    void nullDirectoryThrows() {
      assertThatThrownBy(() -> new PebbleEnvironment(null))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("过滤器注册验证")
  class FilterRegistration {

    @Test
    @DisplayName("format_bytes 过滤器格式化字节数")
    void formatBytesFilter() {
      String result = renderInline("{{ value | format_bytes }}", Map.of("value", 1024));
      assertThat(result).contains("1.0 KB");
    }

    @Test
    @DisplayName("format_duration 过滤器格式化持续时间")
    void formatDurationFilter() {
      String result = renderInline("{{ value | format_duration }}", Map.of("value", 3661));
      assertThat(result).contains("1h 1min");
    }

    @Test
    @DisplayName("precision_label 过滤器映射中文标签")
    void precisionLabelFilter() {
      String result = renderInline("{{ value | precision_label }}", Map.of("value", "estimated"));
      assertThat(result).contains("估算");
    }

    @Test
    @DisplayName("severity_variant 过滤器映射 CSS 变体")
    void severityVariantFilter() {
      String result = renderInline("{{ value | severity_variant }}", Map.of("value", "high"));
      assertThat(result).contains("danger");
    }

    @Test
    @DisplayName("urlencode 过滤器编码 URL")
    void urlEncodeFilter() {
      String result = renderInline("{{ value | urlencode }}", Map.of("value", "hello world"));
      assertThat(result).contains("hello+world");
    }

    @Test
    @DisplayName("safe_html 过滤器直接输出 SafeHtml 内容")
    void safeHtmlFilterWithSafeHtml() {
      SafeHtml safe = SafeHtml.trusted("<b>bold</b>");
      String result = renderInline("{{ value | safe_html }}", Map.of("value", safe));
      assertThat(result).contains("<b>bold</b>");
    }

    @Test
    @DisplayName("safe_html 过滤器转义普通字符串")
    void safeHtmlFilterEscapesString() {
      String result =
          renderInline("{{ value | safe_html }}", Map.of("value", "<script>alert(1)</script>"));
      assertThat(result).doesNotContain("<script>");
      assertThat(result).contains("&lt;script&gt;");
    }

    @Test
    @DisplayName("format_compact_token 过滤器格式化 token 数")
    void formatCompactTokenFilter() {
      String result = renderInline("{{ value | format_compact_token }}", Map.of("value", 1500));
      assertThat(result).contains("1.5K");
    }

    @Test
    @DisplayName("db_agent_to_scope 过滤器转换 agent 值")
    void dbAgentToScopeFilter() {
      String result =
          renderInline("{{ value | db_agent_to_scope }}", Map.of("value", "claude_code"));
      assertThat(result).contains("claude-code");
    }
  }

  @Nested
  @DisplayName("渲染异常处理")
  class RenderException {

    @Test
    @DisplayName("不存在的模板抛出 TemplateRenderException")
    void missingTemplateThrows() {
      PebbleEnvironment env = new PebbleEnvironment();
      assertThatThrownBy(() -> env.render("nonexistent.peb", Map.of()))
          .isInstanceOf(TemplateRenderException.class);
    }
  }

  /**
   * 使用 StringLoader 渲染内联 Pebble 表达式。
   *
   * <p>复用 {@link PebbleEnvironment.PresentationFilterExtension} 保证测试与 production 过滤器一致。 关闭
   * autoescape 以便直接检查过滤器输出。
   */
  private static String renderInline(String expression, Map<String, Object> context) {
    PebbleEngine inlineEngine =
        new PebbleEngine.Builder()
            .loader(new StringLoader())
            .autoEscaping(false)
            .extension(new PebbleEnvironment.PresentationFilterExtension())
            .build();
    try {
      PebbleTemplate template = inlineEngine.getTemplate(expression);
      StringWriter writer = new StringWriter();
      template.evaluate(writer, context);
      return writer.toString();
    } catch (IOException e) {
      throw new TemplateRenderException("内联模板渲染失败", e);
    }
  }
}
