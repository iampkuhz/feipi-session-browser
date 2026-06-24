package com.feipi.session.browser.web.template;

import com.feipi.session.browser.web.model.SafeHtml;
import io.pebbletemplates.pebble.PebbleEngine;
import io.pebbletemplates.pebble.extension.AbstractExtension;
import io.pebbletemplates.pebble.extension.Filter;
import io.pebbletemplates.pebble.loader.ClasspathLoader;
import io.pebbletemplates.pebble.template.EvaluationContext;
import io.pebbletemplates.pebble.template.PebbleTemplate;
import java.io.StringWriter;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Pebble 模板引擎配置与过滤器注册。
 *
 * <p>封装 Pebble 引擎创建过程，注册全部 presentation 层过滤器。 模板输出默认自动转义 HTML， 确保 XSS 安全。
 *
 * <p>过滤器只做显示格式化、URL 编码和转义，不访问数据库或业务逻辑。 全部过滤器与 Python template_env.py 中注册的 Jinja2 filter 一一对应。
 */
public final class PebbleEnvironment {

  private final PebbleEngine engine;

  /**
   * 使用默认 classpath 模板目录创建 Pebble 环境。
   *
   * <p>模板文件从 classpath 的 {@code templates/} 目录加载，输出默认自动转义 HTML。
   */
  public PebbleEnvironment() {
    this("templates");
  }

  /**
   * 使用指定 classpath 模板目录创建 Pebble 环境。
   *
   * @param templateDirectory classpath 下的模板目录路径
   */
  public PebbleEnvironment(String templateDirectory) {
    Objects.requireNonNull(templateDirectory, "templateDirectory 不得为 null");
    ClasspathLoader loader = new ClasspathLoader();
    loader.setPrefix(templateDirectory);
    this.engine =
        new PebbleEngine.Builder()
            .loader(loader)
            .autoEscaping(true)
            .extension(new PresentationFilterExtension())
            .build();
  }

  /**
   * 返回已配置的 Pebble 引擎实例。
   *
   * @return Pebble 引擎
   */
  public PebbleEngine engine() {
    return engine;
  }

  /**
   * 渲染指定模板并返回结果字符串。
   *
   * @param templateName 模板名称（相对于模板目录）
   * @param context 模板变量映射
   * @return 渲染后的 HTML 字符串
   * @throws TemplateRenderException 模板加载或渲染失败时抛出
   */
  public String render(String templateName, Map<String, Object> context) {
    try {
      PebbleTemplate template = engine.getTemplate(templateName);
      StringWriter writer = new StringWriter();
      template.evaluate(writer, context);
      return writer.toString();
    } catch (TemplateRenderException e) {
      throw e;
    } catch (Exception e) {
      throw new TemplateRenderException("模板渲染失败: " + templateName, e);
    }
  }

  /** 注册全部 presentation 层过滤器。 */
  static final class PresentationFilterExtension extends AbstractExtension {

    @Override
    public Map<String, Filter> getFilters() {
      Map<String, Filter> filters = new HashMap<>();

      // ─── 数字格式化 ───
      filters.put(
          "format_bytes", new NoArgFilter(input -> DisplayFormatters.formatBytes(toNumber(input))));
      filters.put(
          "format_compact_token",
          new NoArgFilter(input -> DisplayFormatters.formatCompactToken(toNumber(input))));
      filters.put(
          "format_number",
          new NoArgFilter(input -> DisplayFormatters.formatCompactNum(toNumber(input))));
      filters.put(
          "format_number_short",
          new NoArgFilter(input -> DisplayFormatters.formatCompactNum(toNumber(input))));
      filters.put(
          "format_1d", new NoArgFilter(input -> DisplayFormatters.format1d(toNumber(input))));
      filters.put(
          "format_duration",
          new NoArgFilter(input -> DisplayFormatters.formatDuration(toNumber(input))));
      filters.put(
          "format_coverage",
          new NoArgFilter(input -> DisplayFormatters.formatCoverage(toNumber(input))));

      // ─── 时间格式化 ───
      filters.put(
          "relative_time",
          new NoArgFilter(input -> DisplayFormatters.relativeTime(asString(input))));
      filters.put(
          "local_time", new NoArgFilter(input -> DisplayFormatters.toLocalTime(asString(input))));

      // ─── URL 编码 ───
      filters.put(
          "urlencode", new NoArgFilter(input -> DisplayFormatters.urlEncode(asString(input))));
      filters.put(
          "urldecode", new NoArgFilter(input -> DisplayFormatters.urlDecode(asString(input))));

      // ─── 路径格式化 ───
      filters.put(
          "truncate_path",
          new NoArgFilter(input -> DisplayFormatters.truncatePath(asString(input))));
      filters.put(
          "display_path", new NoArgFilter(input -> DisplayFormatters.displayPath(asString(input))));
      filters.put(
          "shorten_path",
          new OneArgFilter(
              (input, repoRoot) ->
                  DisplayFormatters.shortenPath(
                      asString(input), repoRoot != null ? asString(repoRoot) : null)));
      filters.put(
          "relative_to_repo",
          new OneArgFilter(
              (input, repoRoot) ->
                  DisplayFormatters.relativeToRepo(
                      asString(input), repoRoot != null ? asString(repoRoot) : null)));

      // ─── 行号处理 ───
      filters.put(
          "renumber_lines",
          new NoArgFilter(input -> DisplayFormatters.renumberLines(asString(input))));

      // ─── JSON 序列化 ───
      filters.put("tojson_safe_html", new NoArgFilter(DisplayFormatters::tojsonSafeHtml));
      filters.put("safe_json_display", new NoArgFilter(DisplayFormatters::safeJsonDisplay));
      filters.put(
          "tojson_repo",
          new OneArgFilter(
              (input, repoRoot) ->
                  DisplayFormatters.tojsonRepo(
                      input, repoRoot != null ? asString(repoRoot) : null)));

      // ─── 标签与 CSS 映射 ───
      filters.put(
          "precision_label",
          new NoArgFilter(input -> DisplayFormatters.precisionLabel(asString(input))));
      filters.put(
          "kpi_icon_color", new NoArgFilter(input -> DisplayFormatters.kpiIconColor(toInt(input))));
      filters.put(
          "db_agent_to_scope",
          new NoArgFilter(input -> DisplayFormatters.dbAgentToScope(asString(input))));
      filters.put(
          "scope_to_agent_url",
          new NoArgFilter(input -> DisplayFormatters.scopeToAgentUrl(asString(input))));
      filters.put(
          "severity_variant",
          new NoArgFilter(input -> DisplayFormatters.severityVariant(asString(input))));

      // ─── SafeHtml 支持 ───
      filters.put(
          "safe_html",
          new NoArgFilter(
              input -> {
                if (input instanceof SafeHtml safeHtml) {
                  return safeHtml.value();
                }
                return SafeHtml.escaped(asString(input)).value();
              }));

      return Collections.unmodifiableMap(filters);
    }
  }

  /** 将输入安全转换为字符串。 */
  private static String asString(Object value) {
    return value != null ? value.toString() : "";
  }

  /** 将输入安全转换为 Number。 */
  private static Number toNumber(Object value) {
    if (value instanceof Number num) {
      return num;
    }
    if (value instanceof String s) {
      try {
        return Double.parseDouble(s);
      } catch (NumberFormatException e) {
        return 0;
      }
    }
    return null;
  }

  /** 将输入安全转换为 int。 */
  private static int toInt(Object value) {
    if (value instanceof Number num) {
      return num.intValue();
    }
    return 0;
  }

  /** 无参数过滤器：只接受输入值，委托给格式化函数。 */
  private static final class NoArgFilter implements Filter {
    private final java.util.function.Function<Object, Object> formatter;

    NoArgFilter(java.util.function.Function<Object, Object> formatter) {
      this.formatter = formatter;
    }

    @Override
    public Object apply(
        Object input,
        Map<String, Object> args,
        PebbleTemplate self,
        EvaluationContext context,
        int lineNumber) {
      return formatter.apply(input);
    }

    @Override
    public List<String> getArgumentNames() {
      return Collections.emptyList();
    }
  }

  /** 单参数过滤器函数接口：接受输入值和一个额外参数。 */
  @FunctionalInterface
  private interface BiFormatFunction {
    Object apply(Object input, Object arg);
  }

  /** 单参数过滤器实现：接受输入值和一个额外命名参数 {@code arg0}。 */
  private static final class OneArgFilter implements Filter {
    private final BiFormatFunction formatter;

    OneArgFilter(BiFormatFunction formatter) {
      this.formatter = formatter;
    }

    @Override
    public Object apply(
        Object input,
        Map<String, Object> args,
        PebbleTemplate self,
        EvaluationContext context,
        int lineNumber) {
      Object arg = args.get("arg0");
      return formatter.apply(input, arg);
    }

    @Override
    public List<String> getArgumentNames() {
      return List.of("arg0");
    }
  }
}
