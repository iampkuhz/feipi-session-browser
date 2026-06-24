package com.feipi.session.browser.web.template;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link DisplayFormatters} 显示格式化方法测试。 */
@DisplayName("DisplayFormatters 显示格式化测试")
class DisplayFormattersTest {

  // ─── 数字格式化 ──────────────────────────────────────────────────

  @Nested
  @DisplayName("formatBytes 字节格式化")
  class FormatBytes {

    @Test
    @DisplayName("null 返回 0 B")
    void nullReturnsZero() {
      assertThat(DisplayFormatters.formatBytes(null)).isEqualTo("0 B");
    }

    @Test
    @DisplayName("0 返回 0 B")
    void zeroReturnsZero() {
      assertThat(DisplayFormatters.formatBytes(0)).isEqualTo("0 B");
    }

    @Test
    @DisplayName("小于 1024 返回 B")
    void bytesRange() {
      assertThat(DisplayFormatters.formatBytes(500)).isEqualTo("500 B");
    }

    @Test
    @DisplayName("KB 范围")
    void kbRange() {
      assertThat(DisplayFormatters.formatBytes(1024)).isEqualTo("1.0 KB");
      assertThat(DisplayFormatters.formatBytes(1536)).isEqualTo("1.5 KB");
    }

    @Test
    @DisplayName("MB 范围")
    void mbRange() {
      assertThat(DisplayFormatters.formatBytes(1048576)).isEqualTo("1.0 MB");
    }

    @Test
    @DisplayName("GB 范围")
    void gbRange() {
      assertThat(DisplayFormatters.formatBytes(1073741824L)).isEqualTo("1.0 GB");
    }
  }

  @Nested
  @DisplayName("formatCompactToken token 格式化")
  class FormatCompactToken {

    @Test
    @DisplayName("null 返回 0")
    void nullReturnsZero() {
      assertThat(DisplayFormatters.formatCompactToken(null)).isEqualTo("0");
    }

    @Test
    @DisplayName("小于 1000 直接显示")
    void smallNumber() {
      assertThat(DisplayFormatters.formatCompactToken(500)).isEqualTo("500");
    }

    @Test
    @DisplayName("K 后缀")
    void kSuffix() {
      assertThat(DisplayFormatters.formatCompactToken(1500)).isEqualTo("1.5K");
    }

    @Test
    @DisplayName("M 后缀")
    void mSuffix() {
      assertThat(DisplayFormatters.formatCompactToken(2300000)).isEqualTo("2.3M");
    }
  }

  @Nested
  @DisplayName("format1d 一位小数格式化")
  class Format1d {

    @Test
    @DisplayName("null 返回 0.0")
    void nullReturnsZero() {
      assertThat(DisplayFormatters.format1d(null)).isEqualTo("0.0");
    }

    @Test
    @DisplayName("格式化一位小数")
    void oneDecimal() {
      assertThat(DisplayFormatters.format1d(3.14159)).isEqualTo("3.1");
    }
  }

  @Nested
  @DisplayName("formatDuration 持续时间格式化")
  class FormatDuration {

    @Test
    @DisplayName("null 返回 0s")
    void nullReturnsZero() {
      assertThat(DisplayFormatters.formatDuration(null)).isEqualTo("0s");
    }

    @Test
    @DisplayName("秒数")
    void secondsOnly() {
      assertThat(DisplayFormatters.formatDuration(30)).isEqualTo("30s");
    }

    @Test
    @DisplayName("分钟和秒")
    void minutesAndSeconds() {
      assertThat(DisplayFormatters.formatDuration(120)).isEqualTo("2min 0s");
    }

    @Test
    @DisplayName("小时和分钟")
    void hoursAndMinutes() {
      assertThat(DisplayFormatters.formatDuration(3661)).isEqualTo("1h 1min");
    }
  }

  @Nested
  @DisplayName("formatCoverage 覆盖率格式化")
  class FormatCoverage {

    @Test
    @DisplayName("null 返回破折号")
    void nullReturnsDash() {
      assertThat(DisplayFormatters.formatCoverage(null)).isEqualTo("—");
    }

    @Test
    @DisplayName("百分比格式化")
    void percentageFormat() {
      assertThat(DisplayFormatters.formatCoverage(0.856)).isEqualTo("86%");
    }

    @Test
    @DisplayName("零覆盖率")
    void zeroCoverage() {
      assertThat(DisplayFormatters.formatCoverage(0.0)).isEqualTo("0%");
    }
  }

  // ─── URL 编码 ──────────────────────────────────────────────────

  @Nested
  @DisplayName("URL 编码解码")
  class UrlEncoding {

    @Test
    @DisplayName("urlEncode null 返回空")
    void encodeNull() {
      assertThat(DisplayFormatters.urlEncode(null)).isEmpty();
    }

    @Test
    @DisplayName("urlEncode 编码空格为加号")
    void encodeSpacesAsPlus() {
      assertThat(DisplayFormatters.urlEncode("hello world")).isEqualTo("hello+world");
    }

    @Test
    @DisplayName("urlDecode null 返回空")
    void decodeNull() {
      assertThat(DisplayFormatters.urlDecode(null)).isEmpty();
    }

    @Test
    @DisplayName("编码后解码还原")
    void roundTrip() {
      String original = "test/path?q=中文";
      String encoded = DisplayFormatters.urlEncode(original);
      assertThat(DisplayFormatters.urlDecode(encoded)).isEqualTo(original);
    }
  }

  // ─── 路径格式化 ────────────────────────────────────────────────

  @Nested
  @DisplayName("truncatePath 路径截断")
  class TruncatePath {

    @Test
    @DisplayName("null 返回空")
    void nullReturnsEmpty() {
      assertThat(DisplayFormatters.truncatePath(null)).isEmpty();
    }

    @Test
    @DisplayName("短路径不截断")
    void shortPathUnchanged() {
      assertThat(DisplayFormatters.truncatePath("src/main")).isEqualTo("src/main");
    }

    @Test
    @DisplayName("长路径多段时保留首尾")
    void longPathTruncated() {
      String longPath = "a/b/c/d/e/f/g/h/very/long/path/segments/here";
      String result = DisplayFormatters.truncatePath(longPath);
      assertThat(result).contains("…");
      assertThat(result).startsWith("a/b/");
    }
  }

  @Nested
  @DisplayName("displayPath 主目录替换")
  class DisplayPath {

    @Test
    @DisplayName("null 返回空")
    void nullReturnsEmpty() {
      assertThat(DisplayFormatters.displayPath(null)).isEmpty();
    }

    @Test
    @DisplayName("主目录替换为 ~")
    void homeReplacedWithTilde() {
      String home = System.getProperty("user.home");
      assertThat(DisplayFormatters.displayPath(home)).isEqualTo("~");
    }

    @Test
    @DisplayName("主目录子路径替换为 ~")
    void homeSubdirReplaced() {
      String home = System.getProperty("user.home");
      String subPath = home + "/projects/test";
      assertThat(DisplayFormatters.displayPath(subPath)).startsWith("~");
    }
  }

  // ─── 行号处理 ──────────────────────────────────────────────────

  @Nested
  @DisplayName("renumberLines 行号重编")
  class RenumberLines {

    @Test
    @DisplayName("null 返回 null")
    void nullReturnsNull() {
      assertThat(DisplayFormatters.renumberLines(null)).isNull();
    }

    @Test
    @DisplayName("无行号前缀时原样返回")
    void noLineNumbersUnchanged() {
      assertThat(DisplayFormatters.renumberLines("hello\nworld")).isEqualTo("hello\nworld");
    }

    @Test
    @DisplayName("重新编号行号前缀")
    void renumbersPrefixes() {
      String input = "5\tfirst line\n10\tsecond line\n15\tthird line";
      String result = DisplayFormatters.renumberLines(input);
      assertThat(result).isEqualTo("1\tfirst line\n2\tsecond line\n3\tthird line");
    }
  }

  // ─── JSON 序列化 ──────────────────────────────────────────────

  @Nested
  @DisplayName("tojsonSafeHtml JSON 安全序列化")
  class TojsonSafeHtml {

    @Test
    @DisplayName("null 返回 null 字符串")
    void nullReturnsNullString() {
      assertThat(DisplayFormatters.tojsonSafeHtml(null)).isEqualTo("null");
    }

    @Test
    @DisplayName("字符串值包含引号且被 HTML 转义")
    void stringValueQuoted() {
      // SimpleJson.toJson 先序列化为 JSON，再经 SafeHtml.escaped 转义
      assertThat(DisplayFormatters.tojsonSafeHtml("hello")).contains("&quot;hello&quot;");
    }

    @Test
    @DisplayName("HTML 特殊字符被转义")
    void htmlEscaped() {
      String result = DisplayFormatters.tojsonSafeHtml("<script>");
      assertThat(result).doesNotContain("<script>");
    }
  }

  // ─── 标签和 CSS 映射 ──────────────────────────────────────────

  @Nested
  @DisplayName("precisionLabel 精度标签")
  class PrecisionLabel {

    @Test
    @DisplayName("null 返回不可用")
    void nullReturnsUnavailable() {
      assertThat(DisplayFormatters.precisionLabel(null)).isEqualTo("不可用");
    }

    @Test
    @DisplayName("已知键返回中文标签")
    void knownKeyReturnsChinese() {
      assertThat(DisplayFormatters.precisionLabel("provider_reported")).isEqualTo("实报");
      assertThat(DisplayFormatters.precisionLabel("estimated")).isEqualTo("估算");
    }

    @Test
    @DisplayName("未知键返回原值")
    void unknownKeyReturnsOriginal() {
      assertThat(DisplayFormatters.precisionLabel("custom_key")).isEqualTo("custom_key");
    }
  }

  @Nested
  @DisplayName("kpiIconColor KPI 颜色映射")
  class KpiIconColor {

    @Test
    @DisplayName("1-based 索引循环映射颜色")
    void cyclesColors() {
      assertThat(DisplayFormatters.kpiIconColor(1)).isEqualTo("purple");
      assertThat(DisplayFormatters.kpiIconColor(2)).isEqualTo("blue");
      // 第 7 个应回到第 1 个颜色（列表长度 6）
      assertThat(DisplayFormatters.kpiIconColor(7)).isEqualTo("purple");
    }
  }

  @Nested
  @DisplayName("dbAgentToScope agent 值转换")
  class DbAgentToScope {

    @Test
    @DisplayName("claude_code 转换为 claude-code")
    void claudeCodeConversion() {
      assertThat(DisplayFormatters.dbAgentToScope("claude_code")).isEqualTo("claude-code");
    }

    @Test
    @DisplayName("null 返回 null")
    void nullReturnsNull() {
      assertThat(DisplayFormatters.dbAgentToScope(null)).isNull();
    }
  }

  @Nested
  @DisplayName("severityVariant 严重度 CSS 映射")
  class SeverityVariant {

    @Test
    @DisplayName("null 返回 info")
    void nullReturnsInfo() {
      assertThat(DisplayFormatters.severityVariant(null)).isEqualTo("info");
    }

    @Test
    @DisplayName("high 映射为 danger")
    void highMapsToDanger() {
      assertThat(DisplayFormatters.severityVariant("high")).isEqualTo("danger");
    }

    @Test
    @DisplayName("medium 映射为 warning")
    void mediumMapsToWarning() {
      assertThat(DisplayFormatters.severityVariant("medium")).isEqualTo("warning");
    }

    @Test
    @DisplayName("未知值返回 info")
    void unknownReturnsInfo() {
      assertThat(DisplayFormatters.severityVariant("low")).isEqualTo("info");
    }
  }

  @Nested
  @DisplayName("sumAttribute Map 属性求和")
  class SumAttribute {

    @Test
    @DisplayName("null 列表返回 0")
    void nullListReturnsZero() {
      assertThat(DisplayFormatters.sumAttribute(null, "count")).isEqualTo(0);
    }

    @Test
    @DisplayName("空列表返回 0")
    void emptyListReturnsZero() {
      assertThat(DisplayFormatters.sumAttribute(List.of(), "count")).isEqualTo(0);
    }

    @Test
    @DisplayName("对 Map 列表中的属性求和")
    void sumsMapAttributes() {
      List<Map<String, Object>> items =
          List.of(Map.of("count", 10), Map.of("count", 20), Map.of("count", 30));
      assertThat(DisplayFormatters.sumAttribute(items, "count")).isEqualTo(60);
    }
  }
}
