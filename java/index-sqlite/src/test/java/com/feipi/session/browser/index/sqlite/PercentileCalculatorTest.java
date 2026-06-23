package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.sqlite.PercentileCalculator.MetricKey;
import com.feipi.session.browser.index.sqlite.PercentileCalculator.PercentileResult;
import com.feipi.session.browser.index.sqlite.PercentileCalculator.Thresholds;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 百分位数计算单元测试。
 *
 * <p>覆盖 {@link PercentileCalculator} 的边界值、空列表、单元素和正常分布场景。
 */
@DisplayName("百分位数计算测试")
class PercentileCalculatorTest {

  @Nested
  @DisplayName("percentile")
  class PercentileTests {

    @Test
    @DisplayName("空列表返回 null")
    void emptyListReturnsNull() {
      assertThat(PercentileCalculator.percentile(Collections.emptyList(), 90)).isNull();
    }

    @Test
    @DisplayName("单元素列表返回该元素")
    void singleElementReturnsThatElement() {
      assertThat(PercentileCalculator.percentile(List.of(42.0), 90)).isEqualTo(42.0);
      assertThat(PercentileCalculator.percentile(List.of(42.0), 95)).isEqualTo(42.0);
    }

    @Test
    @DisplayName("P50 返回中位数")
    void p50ReturnsMedian() {
      List<Double> values = List.of(1.0, 2.0, 3.0, 4.0, 5.0);
      assertThat(PercentileCalculator.percentile(values, 50)).isEqualTo(3.0);
    }

    @Test
    @DisplayName("P0 返回最小值")
    void p0ReturnsMin() {
      List<Double> values = List.of(1.0, 2.0, 3.0, 4.0, 5.0);
      assertThat(PercentileCalculator.percentile(values, 0)).isEqualTo(1.0);
    }

    @Test
    @DisplayName("P100 返回最大值")
    void p100ReturnsMax() {
      List<Double> values = List.of(1.0, 2.0, 3.0, 4.0, 5.0);
      assertThat(PercentileCalculator.percentile(values, 100)).isEqualTo(5.0);
    }

    @Test
    @DisplayName("P90 使用线性插值")
    void p90UsesLinearInterpolation() {
      List<Double> values = List.of(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0);
      Double p90 = PercentileCalculator.percentile(values, 90);
      assertThat(p90).isNotNull();
      assertThat(p90).isCloseTo(9.1, org.assertj.core.data.Offset.offset(0.01));
    }

    @Test
    @DisplayName("无序输入正确排序后计算")
    void unorderedInputSortedCorrectly() {
      List<Double> values = List.of(5.0, 1.0, 3.0, 2.0, 4.0);
      assertThat(PercentileCalculator.percentile(values, 50)).isEqualTo(3.0);
    }

    @Test
    @DisplayName("null values 抛出异常")
    void nullValuesThrows() {
      assertThatThrownBy(() -> PercentileCalculator.percentile(null, 90))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("computePercentiles")
  class ComputePercentilesTests {

    @Test
    @DisplayName("空列表返回 null 百分位和零计数")
    void emptyListReturnsNullPercentiles() {
      PercentileResult result = PercentileCalculator.computePercentiles(Collections.emptyList());
      assertThat(result.p90()).isNull();
      assertThat(result.p95()).isNull();
      assertThat(result.count()).isZero();
    }

    @Test
    @DisplayName("正常列表返回完整结果")
    void normalListReturnsCompleteResult() {
      List<Double> values = List.of(1.0, 2.0, 3.0, 4.0, 5.0);
      PercentileResult result = PercentileCalculator.computePercentiles(values);
      assertThat(result.p90()).isNotNull();
      assertThat(result.p95()).isNotNull();
      assertThat(result.count()).isEqualTo(5);
    }
  }

  @Nested
  @DisplayName("getFallbackThreshold")
  class FallbackThresholdTests {

    @Test
    @DisplayName("时长 warning 返回 3600")
    void durationWarningReturns3600() {
      assertThat(PercentileCalculator.getFallbackThreshold(MetricKey.DURATION_SECONDS, "warning"))
          .isEqualTo(3600.0);
    }

    @Test
    @DisplayName("时长 critical 返回 7200")
    void durationCriticalReturns7200() {
      assertThat(PercentileCalculator.getFallbackThreshold(MetricKey.DURATION_SECONDS, "critical"))
          .isEqualTo(7200.0);
    }

    @Test
    @DisplayName("缓存写入 warning 返回 200000")
    void cacheWriteWarningReturns200000() {
      assertThat(PercentileCalculator.getFallbackThreshold(MetricKey.CACHE_WRITE_TOKENS, "warning"))
          .isEqualTo(200_000.0);
    }

    @Test
    @DisplayName("未知严重度的时长指标返回 null")
    void unknownSeverityReturnsNull() {
      assertThat(PercentileCalculator.getFallbackThreshold(MetricKey.DURATION_SECONDS, "unknown"))
          .isNull();
    }
  }

  @Nested
  @DisplayName("computeSessionThresholds")
  class SessionThresholdsTests {

    @Test
    @DisplayName("样本不足时使用回退阈值")
    void insufficientSamplesUseFallback() {
      List<Double> smallSample = List.of(100.0, 200.0, 300.0);
      Map<MetricKey, Thresholds> result =
          PercentileCalculator.computeSessionThresholds(smallSample, smallSample, smallSample);

      Thresholds durationThresholds = result.get(MetricKey.DURATION_SECONDS);
      assertThat(durationThresholds.warning()).isEqualTo(3600.0);
      assertThat(durationThresholds.critical()).isEqualTo(7200.0);
      assertThat(durationThresholds.sampleCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("充足样本时使用 P95")
    void sufficientSamplesUseP95() {
      List<Double> largeSample = new ArrayList<>();
      for (int i = 1; i <= 30; i++) {
        largeSample.add((double) i * 100);
      }

      Map<MetricKey, Thresholds> result =
          PercentileCalculator.computeSessionThresholds(largeSample, largeSample, largeSample);

      Thresholds durationThresholds = result.get(MetricKey.DURATION_SECONDS);
      assertThat(durationThresholds.sampleCount()).isEqualTo(30);
      assertThat(durationThresholds.p95()).isNotNull();
      assertThat(durationThresholds.warning()).isGreaterThan(0);
    }

    @Test
    @DisplayName("空列表使用回退阈值")
    void emptyListUsesFallback() {
      Map<MetricKey, Thresholds> result =
          PercentileCalculator.computeSessionThresholds(
              Collections.emptyList(), Collections.emptyList(), Collections.emptyList());

      Thresholds durationThresholds = result.get(MetricKey.DURATION_SECONDS);
      assertThat(durationThresholds.warning()).isEqualTo(3600.0);
      assertThat(durationThresholds.critical()).isEqualTo(7200.0);
      assertThat(durationThresholds.sampleCount()).isZero();
    }

    @Test
    @DisplayName("结果映射不可变")
    void resultMapIsImmutable() {
      Map<MetricKey, Thresholds> result =
          PercentileCalculator.computeSessionThresholds(
              List.of(1.0), List.of(1.0), List.of(1.0));

      assertThatThrownBy(
              () -> result.put(MetricKey.DURATION_SECONDS, new Thresholds(0, 0, null, null, 0)))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }

  @Nested
  @DisplayName("Thresholds record")
  class ThresholdsRecordTests {

    @Test
    @DisplayName("负 warning 抛出异常")
    void negativeWarningThrows() {
      assertThatThrownBy(() -> new Thresholds(-1, 0, null, null, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("warning 必须非负");
    }

    @Test
    @DisplayName("负 critical 抛出异常")
    void negativeCriticalThrows() {
      assertThatThrownBy(() -> new Thresholds(0, -1, null, null, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("critical 必须非负");
    }

    @Test
    @DisplayName("负 sampleCount 抛出异常")
    void negativeSampleCountThrows() {
      assertThatThrownBy(() -> new Thresholds(0, 0, null, null, -1))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sampleCount 必须非负");
    }
  }
}
