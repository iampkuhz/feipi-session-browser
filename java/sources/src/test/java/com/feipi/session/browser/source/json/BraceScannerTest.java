package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link JsonlReader} 内部辅助方法的单元测试。
 *
 * <p>覆盖 {@code braceCharsOutsideStrings} 和 {@code splitAtDepth0} 的各种场景。
 */
@DisplayName("BraceScanner 内部辅助方法测试")
class BraceScannerTest {

  // ─── 字符串外花括号提取 ────────────────────────────────────────────────

  @Nested
  @DisplayName("braceCharsOutsideStrings")
  class BraceCharsOutsideStringsTests {

    @Test
    @DisplayName("简单对象提取 {}")
    void simpleObject() {
      assertThat(JsonlReader.braceCharsOutsideStrings("{\"a\": 1}")).isEqualTo("{}");
    }

    @Test
    @DisplayName("字符串内的花括号被忽略")
    void bracesInStringIgnored() {
      assertThat(JsonlReader.braceCharsOutsideStrings("{\"key\": \"{value}\"}")).isEqualTo("{}");
    }

    @Test
    @DisplayName("嵌套花括号和方括号")
    void nestedBraces() {
      assertThat(JsonlReader.braceCharsOutsideStrings("{\"a\": {\"b\": [1, 2]}}"))
          .isEqualTo("{{[]}}");
    }

    @Test
    @DisplayName("转义引号不影响状态")
    void escapedQuote() {
      // 输入文本包含转义引号，验证状态机正确处理
      String input = "{\"key\": \"say \\\"hi\\\"\"}";
      assertThat(JsonlReader.braceCharsOutsideStrings(input)).isEqualTo("{}");
    }

    @Test
    @DisplayName("空字符串返回空")
    void emptyString() {
      assertThat(JsonlReader.braceCharsOutsideStrings("")).isEmpty();
    }

    @Test
    @DisplayName("纯文本无花括号返回空")
    void noBraces() {
      assertThat(JsonlReader.braceCharsOutsideStrings("hello world")).isEmpty();
    }

    @Test
    @DisplayName("仅方括号")
    void onlySquareBrackets() {
      assertThat(JsonlReader.braceCharsOutsideStrings("[1, 2, 3]")).isEqualTo("[]");
    }

    @Test
    @DisplayName("双反斜杠后的引号")
    void doubleBackslashThenQuote() {
      // 输入包含双反斜杠转义序列，验证转义状态正确恢复
      String input = "{\"a\": \"test\\\\\"}";
      assertThat(JsonlReader.braceCharsOutsideStrings(input)).isEqualTo("{}");
    }
  }

  // ─── 顶层深度拆分 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("splitAtDepth0")
  class SplitAtDepth0Tests {

    @Test
    @DisplayName("单对象不拆分")
    void noSplitNeeded() {
      assertThat(JsonlReader.splitAtDepth0("{\"a\": 1}")).containsExactly("{\"a\": 1}");
    }

    @Test
    @DisplayName("两个拼接对象")
    void twoConcatenated() {
      List<String> parts = JsonlReader.splitAtDepth0("{\"a\": 1}{\"b\": 2}");
      assertThat(parts).hasSize(2);
      assertThat(parts.get(0)).isEqualTo("{\"a\": 1}");
      assertThat(parts.get(1)).isEqualTo("{\"b\": 2}");
    }

    @Test
    @DisplayName("三个拼接对象")
    void threeConcatenated() {
      List<String> parts = JsonlReader.splitAtDepth0("{\"a\": 1}{\"b\": 2}{\"c\": 3}");
      assertThat(parts).hasSize(3);
    }

    @Test
    @DisplayName("嵌套对象拼接")
    void concatenatedWithNested() {
      List<String> parts = JsonlReader.splitAtDepth0("{\"a\": {\"x\": 1}}{\"b\": 2}");
      assertThat(parts).hasSize(2);
      assertThat(parts.get(0)).isEqualTo("{\"a\": {\"x\": 1}}");
      assertThat(parts.get(1)).isEqualTo("{\"b\": 2}");
    }

    @Test
    @DisplayName("字符串内的 }{ 不作为分割点")
    void stringWithBraceNotSplit() {
      List<String> parts = JsonlReader.splitAtDepth0("{\"k\": \"}{\" }");
      assertThat(parts).containsExactly("{\"k\": \"}{\" }");
    }

    @Test
    @DisplayName("空字符串返回原值")
    void emptyString() {
      assertThat(JsonlReader.splitAtDepth0("")).containsExactly("");
    }
  }
}
