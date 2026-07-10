package com.feipi.session.browser.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.TokenPrecision;
import com.feipi.session.browser.domain.enums.TokenSourceKind;
import com.feipi.session.browser.domain.enums.TokenTotalSemantics;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link NormalizedTokenBreakdown} 测试，覆盖 Jakarta validation 迁移后的不变量验证。
 *
 * <p>生产代码将 ConstraintViolationException 翻译为向后兼容的异常类型：
 *
 * <ul>
 *   <li>{@code @NotNull} 违规翻译为 NullPointerException。
 *   <li>{@code @PositiveOrZero} 违规翻译为 IllegalArgumentException。
 * </ul>
 *
 * <p>同时覆盖 null-as-empty 的 rawFields 和 notes 语义。
 */
@DisplayName("NormalizedTokenBreakdown 测试")
class NormalizedTokenBreakdownTest {

  /** 构建最小有效 NormalizedTokenBreakdown 用于测试。 */
  private static NormalizedTokenBreakdown minimalValid() {
    return new NormalizedTokenBreakdown(
        100L,
        50L,
        20L,
        80L,
        250L,
        TokenPrecision.EXACT,
        TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
        TokenSourceKind.CLAUDE_CODE_JSONL_USAGE,
        Map.of(),
        List.of());
  }

  @Nested
  @DisplayName("正向构造")
  class ValidConstruction {

    @Test
    @DisplayName("有效字段创建成功")
    void validBreakdownCreation() {
      NormalizedTokenBreakdown td = minimalValid();
      assertThat(td.freshInputTokens()).isEqualTo(100L);
      assertThat(td.totalTokens()).isEqualTo(250L);
      assertThat(td.precision()).isEqualTo(TokenPrecision.EXACT);
    }

    @Test
    @DisplayName("全零 token 计数创建成功")
    void zeroTokensAllowed() {
      assertThatCode(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      0L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("empty() 返回全零默认实例")
    void emptyFactory() {
      NormalizedTokenBreakdown empty = NormalizedTokenBreakdown.empty();
      assertThat(empty.freshInputTokens()).isZero();
      assertThat(empty.cacheReadTokens()).isZero();
      assertThat(empty.cacheWriteTokens()).isZero();
      assertThat(empty.outputTokens()).isZero();
      assertThat(empty.totalTokens()).isZero();
      assertThat(empty.precision()).isEqualTo(TokenPrecision.UNKNOWN);
    }
  }

  @Nested
  @DisplayName("负向：token count 为负抛 IllegalArgumentException")
  class NegativeTokenCounts {

    @Test
    @DisplayName("freshInputTokens 为负抛 IllegalArgumentException")
    void negativeFreshInputTokens() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      -1L,
                      0L,
                      0L,
                      0L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("freshInputTokens");
    }

    @Test
    @DisplayName("cacheReadTokens 为负抛 IllegalArgumentException")
    void negativeCacheReadTokens() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      -1L,
                      0L,
                      0L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("cacheReadTokens");
    }

    @Test
    @DisplayName("outputTokens 为负抛 IllegalArgumentException")
    void negativeOutputTokens() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      -1L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("outputTokens");
    }

    @Test
    @DisplayName("totalTokens 为负抛 IllegalArgumentException")
    void negativeTotalTokens() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      0L,
                      -1L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("totalTokens");
    }
  }

  @Nested
  @DisplayName("负向：必填 enum 为 null 抛 NullPointerException")
  class NullEnums {

    @Test
    @DisplayName("precision=null 抛 NullPointerException")
    void nullPrecision() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      0L,
                      0L,
                      null,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("precision");
    }

    @Test
    @DisplayName("totalSemantics=null 抛 NullPointerException")
    void nullTotalSemantics() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      0L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      null,
                      TokenSourceKind.UNKNOWN,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("totalSemantics");
    }

    @Test
    @DisplayName("sourceKind=null 抛 NullPointerException")
    void nullSourceKind() {
      assertThatThrownBy(
              () ->
                  new NormalizedTokenBreakdown(
                      0L,
                      0L,
                      0L,
                      0L,
                      0L,
                      TokenPrecision.UNKNOWN,
                      TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
                      null,
                      Collections.emptyMap(),
                      Collections.emptyList()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("sourceKind");
    }
  }

  @Nested
  @DisplayName("null-as-empty 语义")
  class NullAsEmpty {

    @Test
    @DisplayName("rawFields=null → empty immutable map")
    void nullRawFieldsBecomesEmptyImmutable() {
      NormalizedTokenBreakdown td =
          new NormalizedTokenBreakdown(
              0L,
              0L,
              0L,
              0L,
              0L,
              TokenPrecision.UNKNOWN,
              TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
              TokenSourceKind.UNKNOWN,
              null,
              Collections.emptyList());
      assertThat(td.rawFields()).isEmpty();
    }

    @Test
    @DisplayName("notes=null → empty immutable list")
    void nullNotesBecomesEmptyImmutable() {
      NormalizedTokenBreakdown td =
          new NormalizedTokenBreakdown(
              0L,
              0L,
              0L,
              0L,
              0L,
              TokenPrecision.UNKNOWN,
              TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
              TokenSourceKind.UNKNOWN,
              Collections.emptyMap(),
              null);
      assertThat(td.notes()).isEmpty();
    }

    @Test
    @DisplayName("rawFields 和 notes 不可变")
    void collectionsAreImmutable() {
      NormalizedTokenBreakdown td =
          new NormalizedTokenBreakdown(
              0L,
              0L,
              0L,
              0L,
              0L,
              TokenPrecision.UNKNOWN,
              TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM,
              TokenSourceKind.UNKNOWN,
              new java.util.HashMap<>(Map.of("key", "value")),
              new java.util.ArrayList<>(List.of("note1")));

      assertThat(td.rawFields()).containsEntry("key", "value");
      assertThat(td.notes()).containsExactly("note1");

      org.junit.jupiter.api.Assertions.assertThrows(
          UnsupportedOperationException.class, () -> td.rawFields().put("new", "val"));
      org.junit.jupiter.api.Assertions.assertThrows(
          UnsupportedOperationException.class, () -> td.notes().add("new"));
    }
  }
}
