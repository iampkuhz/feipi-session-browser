package com.feipi.session.browser.contracttest.domain;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.enums.CallStatus;
import com.feipi.session.browser.domain.enums.TokenPrecision;
import com.feipi.session.browser.domain.enums.TokenProvider;
import com.feipi.session.browser.domain.enums.TokenSourceKind;
import com.feipi.session.browser.domain.enums.TokenTotalSemantics;
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 域枚举协议值契约测试。
 *
 * <p>证明六个外部字符串值枚举的 {@code getValue()} 返回值与迁移前完全一致， 确保 Lombok 重构未改变任何公开协议值。 同时验证 {@code getValue()}
 * 方法通过反射仍然可访问， 且 Lombok 不进入运行时 classpath。
 */
@DisplayName("域枚举协议值契约")
class DomainEnumProtocolContractTest {

  /** 验证 {@link CallScope} 全部常量协议值。 */
  @Test
  @DisplayName("CallScope getValue() 与协议值逐字符一致")
  void callScopeValues() {
    Map<CallScope, String> expected = new LinkedHashMap<>();
    expected.put(CallScope.MAIN, "main");
    expected.put(CallScope.SUBAGENT, "subagent");
    assertEnumValues(expected, CallScope::getValue);
  }

  /** 验证 {@link CallStatus} 全部常量协议值。 */
  @Test
  @DisplayName("CallStatus getValue() 与协议值逐字符一致")
  void callStatusValues() {
    Map<CallStatus, String> expected = new LinkedHashMap<>();
    expected.put(CallStatus.OK, "ok");
    expected.put(CallStatus.ERROR, "error");
    assertEnumValues(expected, CallStatus::getValue);
  }

  /** 验证 {@link TokenPrecision} 全部常量协议值。 */
  @Test
  @DisplayName("TokenPrecision getValue() 与协议值逐字符一致")
  void tokenPrecisionValues() {
    Map<TokenPrecision, String> expected = new LinkedHashMap<>();
    expected.put(TokenPrecision.EXACT, "exact");
    expected.put(TokenPrecision.PROVIDER_REPORTED, "provider_reported");
    expected.put(TokenPrecision.ESTIMATED, "estimated");
    expected.put(TokenPrecision.UNKNOWN, "unavailable");
    assertEnumValues(expected, TokenPrecision::getValue);
  }

  /** 验证 {@link TokenProvider} 全部常量协议值。 */
  @Test
  @DisplayName("TokenProvider getValue() 与协议值逐字符一致")
  void tokenProviderValues() {
    Map<TokenProvider, String> expected = new LinkedHashMap<>();
    expected.put(TokenProvider.ANTHROPIC, "anthropic");
    expected.put(TokenProvider.OPENAI, "openai");
    expected.put(TokenProvider.CODEX, "codex");
    expected.put(TokenProvider.QWEN_ANTHROPIC_COMPATIBLE, "qwen-anthropic-compatible");
    expected.put(TokenProvider.QODER, "qoder");
    expected.put(TokenProvider.UNKNOWN, "unknown");
    assertEnumValues(expected, TokenProvider::getValue);
  }

  /** 验证 {@link TokenSourceKind} 全部常量协议值。 */
  @Test
  @DisplayName("TokenSourceKind getValue() 与协议值逐字符一致")
  void tokenSourceKindValues() {
    Map<TokenSourceKind, String> expected = new LinkedHashMap<>();
    expected.put(TokenSourceKind.CLAUDE_CODE_JSONL_USAGE, "claude_code_jsonl_usage");
    expected.put(TokenSourceKind.CODEX_ROLLOUT_TOKEN_COUNT, "codex_rollout_token_count");
    expected.put(TokenSourceKind.OPENAI_RESPONSES_USAGE, "openai_responses_usage");
    expected.put(
        TokenSourceKind.QODER_SEGMENT_MODEL_RESPONSE_COMPLETED,
        "qoder_segment_model_response_completed");
    expected.put(TokenSourceKind.QODER_SQLITE_TOKEN_INFO, "qoder_sqlite_token_info");
    expected.put(TokenSourceKind.QODER_TURN_FINISHED_FALLBACK, "qoder_turn_finished_fallback");
    expected.put(TokenSourceKind.QODER_TRANSCRIPT_ESTIMATED, "qoder_transcript_estimated");
    expected.put(TokenSourceKind.SESSION_TOTAL_ONLY_FALLBACK, "session_total_only_fallback");
    expected.put(TokenSourceKind.UNKNOWN, "unknown");
    assertEnumValues(expected, TokenSourceKind::getValue);
  }

  /** 验证 {@link TokenTotalSemantics} 全部常量协议值。 */
  @Test
  @DisplayName("TokenTotalSemantics getValue() 与协议值逐字符一致")
  void tokenTotalSemanticsValues() {
    Map<TokenTotalSemantics, String> expected = new LinkedHashMap<>();
    expected.put(TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM, "exclusive_components_sum");
    expected.put(TokenTotalSemantics.REPORTED_TOTAL, "reported_total");
    expected.put(TokenTotalSemantics.REPORTED_CUMULATIVE_DELTA, "reported_cumulative_delta");
    expected.put(TokenTotalSemantics.PROMPT_TOTAL_PLUS_OUTPUT, "prompt_total_plus_output");
    expected.put(TokenTotalSemantics.ESTIMATED_COMPONENT_SUM, "estimated_components_sum");
    expected.put(
        TokenTotalSemantics.RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL,
        "recomputed_due_to_inconsistent_raw_total");
    assertEnumValues(expected, TokenTotalSemantics::getValue);
  }

  /** 验证所有六个枚举常量数量与迁移前一致。 */
  @Test
  @DisplayName("六个枚举常量数量不变")
  void enumConstantCountsPreserved() {
    assertThat(CallScope.values()).hasSize(2);
    assertThat(CallStatus.values()).hasSize(2);
    assertThat(TokenPrecision.values()).hasSize(4);
    assertThat(TokenProvider.values()).hasSize(6);
    assertThat(TokenSourceKind.values()).hasSize(9);
    assertThat(TokenTotalSemantics.values()).hasSize(6);
  }

  /** 验证 {@code getValue()} 公开方法通过反射可访问。 */
  @Test
  @DisplayName("getValue() 公开方法在所有六个枚举上存在")
  void getValueMethodExistsOnAllEnums() throws Exception {
    Class<?>[] enums = {
      CallScope.class,
      CallStatus.class,
      TokenPrecision.class,
      TokenProvider.class,
      TokenSourceKind.class,
      TokenTotalSemantics.class,
    };
    for (Class<?> enumClass : enums) {
      Method getValue = enumClass.getMethod("getValue");
      assertThat(getValue).isNotNull();
      assertThat(getValue.getReturnType()).isEqualTo(String.class);
      assertThat(getValue.getParameterCount()).isZero();
    }
  }

  /** 验证 Lombok 不进入运行时 classpath。 */
  @Test
  @DisplayName("Lombok 不在运行时 classpath 中")
  void lombokNotInRuntimeClasspath() {
    assertThat(isLombokAvailable()).as("lombok 不应在运行时 classpath 中；它应为 compileOnly 依赖").isFalse();
  }

  /** 断言枚举常量与期望协议值逐字符一致。 */
  private static <E extends Enum<E>> void assertEnumValues(
      Map<E, String> expected, Function<E, String> valueExtractor) {
    for (Map.Entry<E, String> entry : expected.entrySet()) {
      E constant = entry.getKey();
      String expectedValue = entry.getValue();
      String actualValue = valueExtractor.apply(constant);
      assertThat(actualValue)
          .as(
              "枚举 %s.%s 的 getValue() 应与协议值一致",
              constant.getDeclaringClass().getSimpleName(), constant.name())
          .isEqualTo(expectedValue);
    }
  }

  /** 检测 Lombok 是否在运行时可用。 */
  private static boolean isLombokAvailable() {
    try {
      Class.forName("lombok.Getter");
      return true;
    } catch (ClassNotFoundException e) {
      return false;
    }
  }
}
