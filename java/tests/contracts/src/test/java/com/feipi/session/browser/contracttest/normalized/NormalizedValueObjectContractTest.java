package com.feipi.session.browser.contracttest.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 归一化基础值对象合约测试。
 *
 * <p>覆盖 {@link ByteRange}、{@link NormalizedCallUsage}、 {@link NormalizedCallRequest}、{@link
 * NormalizedCallResponse} 的不变量正负向路径。 每条不变量均有正向构造验证和负向异常验证。
 */
@DisplayName("归一化基础值对象合约测试")
class NormalizedValueObjectContractTest {

  @Nested
  @DisplayName("ByteRange 合约")
  class ByteRangeContract {

    @Test
    @DisplayName("正向：合法字节范围构造成功")
    void validRange() {
      ByteRange range = new ByteRange(0, 100);
      assertThat(range.start()).isEqualTo(0);
      assertThat(range.end()).isEqualTo(100);
    }

    @Test
    @DisplayName("正向：零长度范围合法")
    void zeroLengthRange() {
      ByteRange range = new ByteRange(50, 50);
      assertThat(range.start()).isEqualTo(50);
      assertThat(range.end()).isEqualTo(50);
    }

    @Test
    @DisplayName("正向：empty() 返回零范围")
    void emptyRange() {
      ByteRange range = ByteRange.empty();
      assertThat(range.start()).isZero();
      assertThat(range.end()).isZero();
    }

    @Test
    @DisplayName("负向：start 为负数抛出异常")
    void negativeStart() {
      assertThatThrownBy(() -> new ByteRange(-1, 10))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("start");
    }

    @Test
    @DisplayName("负向：end 为负数抛出异常")
    void negativeEnd() {
      assertThatThrownBy(() -> new ByteRange(0, -1))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("end");
    }

    @Test
    @DisplayName("负向：end 小于 start 抛出异常")
    void endLessThanStart() {
      assertThatThrownBy(() -> new ByteRange(10, 5))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("end must be >= start");
    }
  }

  @Nested
  @DisplayName("NormalizedCallUsage 合约")
  class CallUsageContract {

    @Test
    @DisplayName("正向：合法 token 用量构造成功")
    void validUsage() {
      NormalizedCallUsage usage = new NormalizedCallUsage(100, 50, 20, 80, 250);
      assertThat(usage.fresh()).isEqualTo(100);
      assertThat(usage.cacheRead()).isEqualTo(50);
      assertThat(usage.cacheWrite()).isEqualTo(20);
      assertThat(usage.output()).isEqualTo(80);
      assertThat(usage.total()).isEqualTo(250);
    }

    @Test
    @DisplayName("正向：全零用法合法")
    void zeroUsage() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      assertThat(usage.total()).isZero();
    }

    @Test
    @DisplayName("负向：fresh 为负数抛出异常")
    void negativeFresh() {
      assertThatThrownBy(() -> new NormalizedCallUsage(-1, 0, 0, 0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("fresh");
    }

    @Test
    @DisplayName("负向：total 不等于分量之和抛出异常")
    void totalMismatch() {
      assertThatThrownBy(() -> new NormalizedCallUsage(100, 50, 20, 80, 999))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("component sum");
    }

    @Test
    @DisplayName("负向：total 为负数抛出异常")
    void negativeTotal() {
      assertThatThrownBy(() -> new NormalizedCallUsage(0, 0, 0, 0, -1))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("total");
    }
  }

  @Nested
  @DisplayName("NormalizedCallRequest 合约")
  class CallRequestContract {

    @Test
    @DisplayName("正向：合法请求构造成功")
    void validRequest() {
      NormalizedCallRequest request = new NormalizedCallRequest(List.of("tool1", "tool2"));
      assertThat(request.toolResultIds()).containsExactly("tool1", "tool2");
    }

    @Test
    @DisplayName("正向：空请求合法")
    void emptyRequest() {
      NormalizedCallRequest request = NormalizedCallRequest.empty();
      assertThat(request.toolResultIds()).isEmpty();
    }

    @Test
    @DisplayName("正向：null 输入规范化为空列表")
    void nullInputNormalized() {
      NormalizedCallRequest request = new NormalizedCallRequest(null);
      assertThat(request.toolResultIds()).isEmpty();
    }

    @Test
    @DisplayName("正向：防御性拷贝，外部修改不影响内部")
    void defensiveCopy() {
      var mutableList = new java.util.ArrayList<>(List.of("a", "b"));
      NormalizedCallRequest request = new NormalizedCallRequest(mutableList);
      mutableList.add("c");
      assertThat(request.toolResultIds()).containsExactly("a", "b");
    }
  }

  @Nested
  @DisplayName("NormalizedCallResponse 合约")
  class CallResponseContract {

    @Test
    @DisplayName("正向：合法响应构造成功")
    void validResponse() {
      NormalizedCallResponse response = new NormalizedCallResponse(List.of("call1"));
      assertThat(response.toolCallIds()).containsExactly("call1");
    }

    @Test
    @DisplayName("正向：空响应合法")
    void emptyResponse() {
      NormalizedCallResponse response = NormalizedCallResponse.empty();
      assertThat(response.toolCallIds()).isEmpty();
    }

    @Test
    @DisplayName("正向：null 输入规范化为空列表")
    void nullInputNormalized() {
      NormalizedCallResponse response = new NormalizedCallResponse(null);
      assertThat(response.toolCallIds()).isEmpty();
    }
  }
}
