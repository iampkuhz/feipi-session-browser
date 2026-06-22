package com.feipi.session.browser.contracttest.sourcespi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceOutcome;
import com.feipi.session.browser.source.spi.SourceResult;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceOutcome} 和 {@link SourceResult} 密封类型契约测试。
 *
 * <p>验证四种状态的完整性、禁止 null/boolean 歧义、sealed 模式匹配覆盖。
 */
@DisplayName("Source SPI — SourceOutcome 与 SourceResult 密封类型契约")
class SourceOutcomeContractTest {

  @Test
  @DisplayName("四种状态全部存在")
  void allFourOutcomesExist() {
    assertThat(SourceOutcome.values()).hasSize(4);
    assertThat(SourceOutcome.valueOf("SUCCESS")).isNotNull();
    assertThat(SourceOutcome.valueOf("RETRYABLE_INCOMPLETE")).isNotNull();
    assertThat(SourceOutcome.valueOf("SKIPPED")).isNotNull();
    assertThat(SourceOutcome.valueOf("FATAL")).isNotNull();
  }

  @Test
  @DisplayName("isSuccess/isRetryable/isFatal 语义正确")
  void outcomePredicatesCorrect() {
    assertThat(SourceOutcome.SUCCESS.isSuccess()).isTrue();
    assertThat(SourceOutcome.SUCCESS.isRetryable()).isFalse();
    assertThat(SourceOutcome.SUCCESS.isFatal()).isFalse();

    assertThat(SourceOutcome.RETRYABLE_INCOMPLETE.isSuccess()).isFalse();
    assertThat(SourceOutcome.RETRYABLE_INCOMPLETE.isRetryable()).isTrue();
    assertThat(SourceOutcome.RETRYABLE_INCOMPLETE.isFatal()).isFalse();

    assertThat(SourceOutcome.SKIPPED.isSuccess()).isFalse();
    assertThat(SourceOutcome.SKIPPED.isRetryable()).isFalse();
    assertThat(SourceOutcome.SKIPPED.isFatal()).isFalse();

    assertThat(SourceOutcome.FATAL.isSuccess()).isFalse();
    assertThat(SourceOutcome.FATAL.isRetryable()).isFalse();
    assertThat(SourceOutcome.FATAL.isFatal()).isTrue();
  }

  @Test
  @DisplayName("Success 结果 outcome 为 SUCCESS")
  void successResult() {
    SourceResult.Success result = new SourceResult.Success(List.of(), 5);
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    assertThat(result.candidateCount()).isEqualTo(5);
    assertThat(result.diagnostics()).isEmpty();
    assertThat(result.message()).contains("成功");
  }

  @Test
  @DisplayName("RetryableIncomplete 结果 outcome 为 RETRYABLE_INCOMPLETE")
  void retryableResult() {
    SourceResult.RetryableIncomplete result =
        new SourceResult.RetryableIncomplete(List.of(), "文件正在写入");
    assertThat(result.outcome()).isEqualTo(SourceOutcome.RETRYABLE_INCOMPLETE);
    assertThat(result.reason()).isEqualTo("文件正在写入");
    assertThat(result.message()).contains("可重试");
  }

  @Test
  @DisplayName("Skipped 结果 outcome 为 SKIPPED")
  void skippedResult() {
    SourceResult.Skipped result = new SourceResult.Skipped(List.of(), "目录不存在");
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SKIPPED);
    assertThat(result.reason()).isEqualTo("目录不存在");
    assertThat(result.message()).contains("跳过");
  }

  @Test
  @DisplayName("Fatal 结果 outcome 为 FATAL")
  void fatalResult() {
    SourceResult.Fatal result = new SourceResult.Fatal(List.of(), "权限拒绝");
    assertThat(result.outcome()).isEqualTo(SourceOutcome.FATAL);
    assertThat(result.errorDetail()).isEqualTo("权限拒绝");
    assertThat(result.message()).contains("致命错误");
  }

  @Test
  @DisplayName("结果可携带诊断信息")
  void resultWithDiagnostics() {
    SourceDiagnostic diag =
        new SourceDiagnostic(
            ParseSeverity.WARNING,
            ParseIssueType.NON_OBJECT_SKIPPED,
            "跳过非对象",
            10,
            Optional.empty());
    SourceResult.Success result = new SourceResult.Success(List.of(diag), 3);
    assertThat(result.diagnostics()).hasSize(1);
    assertThat(result.diagnostics().get(0).severity()).isEqualTo(ParseSeverity.WARNING);
  }

  @Test
  @DisplayName("Success 负候选项数量抛出异常")
  void negativeCandidateCountRejected() {
    assertThatThrownBy(() -> new SourceResult.Success(List.of(), -1))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("candidateCount");
  }

  @Test
  @DisplayName("RetryableIncomplete 空 reason 抛出异常")
  void emptyRetryableReasonRejected() {
    assertThatThrownBy(() -> new SourceResult.RetryableIncomplete(List.of(), ""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("reason");
  }

  @Test
  @DisplayName("Skipped null reason 抛出异常")
  void nullSkippedReasonRejected() {
    assertThatThrownBy(() -> new SourceResult.Skipped(List.of(), null))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("Fatal 空 errorDetail 抛出异常")
  void emptyFatalDetailRejected() {
    assertThatThrownBy(() -> new SourceResult.Fatal(List.of(), ""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("errorDetail");
  }

  @Test
  @DisplayName("sealed 模式匹配覆盖所有分支")
  void sealedPatternMatchingExhaustive() {
    SourceResult[] results = {
      new SourceResult.Success(List.of(), 1),
      new SourceResult.RetryableIncomplete(List.of(), "retry"),
      new SourceResult.Skipped(List.of(), "skip"),
      new SourceResult.Fatal(List.of(), "fatal")
    };
    for (SourceResult r : results) {
      String label =
          switch (r) {
            case SourceResult.Success s -> "success:" + s.candidateCount();
            case SourceResult.RetryableIncomplete ri -> "retry:" + ri.reason();
            case SourceResult.Skipped sk -> "skip:" + sk.reason();
            case SourceResult.Fatal f -> "fatal:" + f.errorDetail();
          };
      assertThat(label).isNotEmpty();
    }
  }

  @Test
  @DisplayName("诊断列表不可变")
  void diagnosticsImmutable() {
    SourceResult.Success result = new SourceResult.Success(List.of(), 0);
    assertThatThrownBy(
            () ->
                result
                    .diagnostics()
                    .add(
                        new SourceDiagnostic(
                            ParseSeverity.INFO, ParseIssueType.BAD_JSON, "x", 1, Optional.empty())))
        .isInstanceOf(UnsupportedOperationException.class);
  }
}
