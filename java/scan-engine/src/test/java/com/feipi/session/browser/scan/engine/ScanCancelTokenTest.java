package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.CancellationException;
import org.junit.jupiter.api.Test;

/**
 * {@link ScanCancelToken} 单元测试。
 *
 * <p>覆盖单向取消语义、幂等性和 throwIfCancelled 行为。
 */
class ScanCancelTokenTest {

  @Test
  void initiallyNotCancelled() {
    ScanCancelToken token = new ScanCancelToken();
    assertThat(token.isCancelled()).isFalse();
  }

  @Test
  void cancelSetsFlag() {
    ScanCancelToken token = new ScanCancelToken();
    token.cancel();
    assertThat(token.isCancelled()).isTrue();
  }

  @Test
  void cancelIsIdempotent() {
    ScanCancelToken token = new ScanCancelToken();
    token.cancel();
    token.cancel();
    assertThat(token.isCancelled()).isTrue();
  }

  @Test
  void throwIfCancelledDoesNothingWhenNotCancelled() {
    ScanCancelToken token = new ScanCancelToken();
    token.throwIfCancelled(); // 不应抛出
  }

  @Test
  void throwIfCancelledThrowsAfterCancel() {
    ScanCancelToken token = new ScanCancelToken();
    token.cancel();
    assertThatThrownBy(token::throwIfCancelled).isInstanceOf(CancellationException.class);
  }
}
