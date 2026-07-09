package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

/** {@link PageResult} 契约测试。 */
class PageResultTest {

  @Test
  void ofOffsetNoCursor() {
    PageResult<String> result = PageResult.ofOffset(List.of("a", "b", "c"), 100);
    assertThat(result.items()).containsExactly("a", "b", "c");
    assertThat(result.totalCount()).isEqualTo(100);
    assertThat(result.nextCursor()).isEmpty();
    assertThat(result.hasMore()).isFalse();
    assertThat(result.size()).isEqualTo(3);
    assertThat(result.isEmpty()).isFalse();
  }

  @Test
  void ofCursorWithNextCursor() {
    PageResult<String> result = PageResult.ofCursor(List.of("a"), 100, "next-page");
    assertThat(result.items()).containsExactly("a");
    assertThat(result.totalCount()).isEqualTo(100);
    assertThat(result.nextCursor()).isEqualTo("next-page");
    assertThat(result.hasMore()).isTrue();
  }

  @Test
  void ofCursorUnspecifiedTotalCount() {
    PageResult<String> result = PageResult.ofCursor(List.of("a"), -1, "next");
    assertThat(result.totalCount()).isEqualTo(-1);
  }

  @Test
  void emptyResult() {
    PageResult<String> result = PageResult.ofOffset(List.of(), 0);
    assertThat(result.isEmpty()).isTrue();
    assertThat(result.size()).isZero();
    assertThat(result.hasMore()).isFalse();
  }

  @Test
  void defensiveCopyItemsImmutable() {
    List<String> mutable = new java.util.ArrayList<>(List.of("a", "b"));
    PageResult<String> result = PageResult.ofOffset(mutable, 2);
    mutable.add("c");
    assertThat(result.items()).containsExactly("a", "b");
  }

  @Test
  void nullItemsRejected() {
    assertThatThrownBy(() -> new PageResult<>(null, 0, ""))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("items");
  }

  @Test
  void nullNextCursorRejected() {
    assertThatThrownBy(() -> new PageResult<>(List.of(), 0, null))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("nextCursor");
  }

  @Test
  void negativeTotalCountBelowMinusOneRejected() {
    assertThatThrownBy(() -> new PageResult<>(List.of(), -2, ""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("totalCount");
  }
}
