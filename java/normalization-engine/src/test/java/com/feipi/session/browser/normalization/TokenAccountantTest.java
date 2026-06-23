package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link TokenAccountant} 单元测试。
 *
 * <p>验证单调用 token 提取和多调用聚合逻辑。
 */
@DisplayName("TokenAccountant token 核算器测试")
class TokenAccountantTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Nested
  @DisplayName("extractUsage")
  class ExtractUsageTests {

    @Test
    @DisplayName("null 事件返回零用量")
    void nullEventReturnsEmptyUsage() {
      NormalizedCallUsage usage = TokenAccountant.extractUsage(null);
      assertThat(usage.total()).isZero();
      assertThat(usage.fresh()).isZero();
    }

    @Test
    @DisplayName("无 usage 字段返回零用量")
    void noUsageFieldReturnsEmptyUsage() {
      ObjectNode event = MAPPER.createObjectNode().put("type", "assistant");
      NormalizedCallUsage usage = TokenAccountant.extractUsage(TestSourceRecords.from(event, 0));
      assertThat(usage.total()).isZero();
    }

    @Test
    @DisplayName("完整 usage 正确提取")
    void fullUsageExtractedCorrectly() {
      ObjectNode event = MAPPER.createObjectNode();
      ObjectNode usage = event.putObject("usage");
      usage.put("input_tokens", 100);
      usage.put("cache_read_input_tokens", 50);
      usage.put("cache_creation_input_tokens", 25);
      usage.put("output_tokens", 200);

      NormalizedCallUsage result = TokenAccountant.extractUsage(TestSourceRecords.from(event, 0));
      assertThat(result.fresh()).isEqualTo(100);
      assertThat(result.cacheRead()).isEqualTo(50);
      assertThat(result.cacheWrite()).isEqualTo(25);
      assertThat(result.output()).isEqualTo(200);
      assertThat(result.total()).isEqualTo(375);
    }
  }

  @Nested
  @DisplayName("aggregate")
  class AggregateTests {

    @Test
    @DisplayName("空列表返回零用量")
    void emptyListReturnsEmptyUsage() {
      NormalizedCallUsage result = TokenAccountant.aggregate(List.of());
      assertThat(result.total()).isZero();
      assertThat(result.fresh()).isZero();
      assertThat(result.output()).isZero();
    }

    @Test
    @DisplayName("null 列表返回零用量")
    void nullListReturnsEmptyUsage() {
      NormalizedCallUsage result = TokenAccountant.aggregate(null);
      assertThat(result.total()).isZero();
    }

    @Test
    @DisplayName("单个用量聚合等于其本身")
    void singleUsageAggregateEqualsSelf() {
      NormalizedCallUsage single = new NormalizedCallUsage(100, 50, 25, 200, 375);
      NormalizedCallUsage result = TokenAccountant.aggregate(List.of(single));
      assertThat(result.fresh()).isEqualTo(100);
      assertThat(result.cacheRead()).isEqualTo(50);
      assertThat(result.cacheWrite()).isEqualTo(25);
      assertThat(result.output()).isEqualTo(200);
      assertThat(result.total()).isEqualTo(375);
    }

    @Test
    @DisplayName("多个用量正确聚合")
    void multipleUsagesAggregatedCorrectly() {
      NormalizedCallUsage usage1 = new NormalizedCallUsage(100, 50, 25, 200, 375);
      NormalizedCallUsage usage2 = new NormalizedCallUsage(200, 100, 75, 400, 775);

      NormalizedCallUsage result = TokenAccountant.aggregate(List.of(usage1, usage2));
      assertThat(result.fresh()).isEqualTo(300);
      assertThat(result.cacheRead()).isEqualTo(150);
      assertThat(result.cacheWrite()).isEqualTo(100);
      assertThat(result.output()).isEqualTo(600);
      assertThat(result.total()).isEqualTo(1150);
    }

    @Test
    @DisplayName("聚合包含零用量的调用")
    void aggregateIncludesZeroUsageCalls() {
      NormalizedCallUsage usage1 = new NormalizedCallUsage(100, 0, 0, 200, 300);
      NormalizedCallUsage zero = NormalizedCallUsage.empty();

      NormalizedCallUsage result = TokenAccountant.aggregate(List.of(usage1, zero));
      assertThat(result.fresh()).isEqualTo(100);
      assertThat(result.output()).isEqualTo(200);
      assertThat(result.total()).isEqualTo(300);
    }

    @Test
    @DisplayName("聚合保证 total 不变量")
    void aggregatePreservesTotalInvariant() {
      NormalizedCallUsage usage1 = new NormalizedCallUsage(10, 20, 30, 40, 100);
      NormalizedCallUsage usage2 = new NormalizedCallUsage(5, 15, 25, 35, 80);
      NormalizedCallUsage usage3 = new NormalizedCallUsage(1, 2, 3, 4, 10);

      NormalizedCallUsage result = TokenAccountant.aggregate(List.of(usage1, usage2, usage3));
      long expectedTotal =
          result.fresh() + result.cacheRead() + result.cacheWrite() + result.output();
      assertThat(result.total()).isEqualTo(expectedTotal);
    }
  }
}
