package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * query-api 详情相关类型测试。
 *
 * <p>覆盖 {@link CallRound}、{@link PayloadSource}、{@link PayloadSourceKind}、
 * {@link PayloadVisibility} 和 {@link SensitiveFieldPolicy} 的不变量和边界。
 */
@DisplayName("query-api 详情类型测试")
class DetailTypesTest {

  @Nested
  @DisplayName("CallRound")
  class CallRoundTest {

    @Test
    @DisplayName("合法构造")
    void validConstruction() {
      CallRound round = CallRound.of(1, java.util.List.of("c1", "c2"), java.util.List.of("t1"));
      assertThat(round.roundIndex()).isEqualTo(1);
      assertThat(round.callCount()).isEqualTo(2);
      assertThat(round.toolCallCount()).isEqualTo(1);
      assertThat(round.isEmpty()).isFalse();
    }

    @Test
    @DisplayName("roundIndex < 1 抛出异常")
    void invalidRoundIndex() {
      assertThatThrownBy(() -> CallRound.of(0, java.util.List.of(), java.util.List.of()))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("空轮次 isEmpty 返回 true")
    void emptyRound() {
      CallRound round = CallRound.of(1, java.util.List.of(), java.util.List.of());
      assertThat(round.isEmpty()).isTrue();
    }

    @Test
    @DisplayName("null calls 抛出异常")
    void nullCalls() {
      assertThatThrownBy(() -> new CallRound(1, null, java.util.List.of(), null))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("PayloadSource")
  class PayloadSourceTest {

    @Test
    @DisplayName("合法构造")
    void validConstruction() {
      PayloadSource source =
          new PayloadSource("p1", PayloadSourceKind.LLM_REQUEST, "c1", "Request C1", true);
      assertThat(source.payloadId()).isEqualTo("p1");
      assertThat(source.kind()).isEqualTo(PayloadSourceKind.LLM_REQUEST);
      assertThat(source.truncated()).isTrue();
    }

    @Test
    @DisplayName("空 payloadId 抛出异常")
    void emptyPayloadId() {
      assertThatThrownBy(
              () -> new PayloadSource("", PayloadSourceKind.LLM_REQUEST, "c1", "", false))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("空 callId 抛出异常")
    void emptyCallId() {
      assertThatThrownBy(
              () -> new PayloadSource("p1", PayloadSourceKind.LLM_REQUEST, "", "", false))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("full factory 不截断")
    void fullFactory() {
      PayloadSource source = PayloadSource.full("p1", PayloadSourceKind.LLM_RESPONSE, "c1");
      assertThat(source.truncated()).isFalse();
      assertThat(source.title()).isEmpty();
    }
  }

  @Nested
  @DisplayName("PayloadSourceKind")
  class PayloadSourceKindTest {

    @Test
    @DisplayName("全部枚举值存在")
    void allValuesExist() {
      assertThat(PayloadSourceKind.values())
          .containsExactly(
              PayloadSourceKind.LLM_REQUEST,
              PayloadSourceKind.LLM_RESPONSE,
              PayloadSourceKind.TOOL_RESULT,
              PayloadSourceKind.SUBAGENT_REQUEST,
              PayloadSourceKind.SUBAGENT_RESPONSE);
    }
  }

  @Nested
  @DisplayName("SensitiveFieldPolicy")
  class SensitiveFieldPolicyTest {

    @Test
    @DisplayName("默认策略包含常见敏感字段")
    void defaultFields() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.DEFAULT;
      assertThat(policy.isSensitive("api_key")).isTrue();
      assertThat(policy.isSensitive("token")).isTrue();
      assertThat(policy.isSensitive("password")).isTrue();
      assertThat(policy.isSensitive("project_key")).isFalse();
    }

    @Test
    @DisplayName("noMasking 策略不隐藏任何字段")
    void noMaskingPolicy() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.noMasking();
      assertThat(policy.isSensitive("api_key")).isFalse();
      assertThat(policy.maskingEnabled()).isFalse();
    }

    @Test
    @DisplayName("fromVisibility 映射正确")
    void fromVisibilityMapping() {
      assertThat(SensitiveFieldPolicy.fromVisibility(PayloadVisibility.STANDARD).maskingEnabled())
          .isTrue();
      assertThat(SensitiveFieldPolicy.fromVisibility(PayloadVisibility.FULL).maskingEnabled())
          .isFalse();
    }

    @Test
    @DisplayName("applyMasking 替换 key=value 格式")
    void maskingKeyValue() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.DEFAULT;
      String result = policy.applyMasking("api_key=secret123 other=visible");
      assertThat(result).contains("[REDACTED]");
      assertThat(result).doesNotContain("secret123");
      assertThat(result).contains("other=visible");
    }

    @Test
    @DisplayName("applyMasking 替换 key: value 格式")
    void maskingColonFormat() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.DEFAULT;
      String result = policy.applyMasking("token: abc123def");
      assertThat(result).contains("[REDACTED]");
      assertThat(result).doesNotContain("abc123def");
    }

    @Test
    @DisplayName("applyMasking null 安全")
    void maskingNull() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.DEFAULT;
      assertThat(policy.applyMasking(null)).isNull();
      assertThat(policy.applyMasking("")).isEmpty();
    }

    @Test
    @DisplayName("noMasking 策略不修改内容")
    void noMaskingNoChange() {
      SensitiveFieldPolicy policy = SensitiveFieldPolicy.noMasking();
      String content = "api_key=secret123";
      assertThat(policy.applyMasking(content)).isEqualTo(content);
    }
  }
}
