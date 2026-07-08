package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link PageRequest} 契约测试。 */
class PageRequestTest {

  @Test
  void defaultsAreOffsetZeroLimit50() {
    PageRequest req = PageRequest.DEFAULT;
    assertThat(req.offset()).isZero();
    assertThat(req.limit()).isEqualTo(50);
    assertThat(req.cursor()).isEmpty();
    assertThat(req.isCursorMode()).isFalse();
  }

  @Nested
  class OffsetMode {

    @Test
    void ofOffsetValidParams() {
      PageRequest req = PageRequest.ofOffset(100, 25);
      assertThat(req.offset()).isEqualTo(100);
      assertThat(req.limit()).isEqualTo(25);
      assertThat(req.cursor()).isEmpty();
      assertThat(req.isCursorMode()).isFalse();
    }

    @Test
    void ofOffsetZeroIsValid() {
      PageRequest req = PageRequest.ofOffset(0, 50);
      assertThat(req.offset()).isZero();
    }

    @Test
    void ofOffsetMaxLimitIsValid() {
      PageRequest req = PageRequest.ofOffset(0, 500);
      assertThat(req.limit()).isEqualTo(500);
    }

    @Test
    void ofOffsetNegativeOffsetRejected() {
      assertThatThrownBy(() -> PageRequest.ofOffset(-1, 50))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("offset 必须非负");
    }

    @Test
    void ofOffsetZeroLimitRejected() {
      assertThatThrownBy(() -> PageRequest.ofOffset(0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("limit 必须在");
    }

    @Test
    void ofOffsetOverMaxLimitRejected() {
      assertThatThrownBy(() -> PageRequest.ofOffset(0, 501))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("limit 必须在");
    }
  }

  @Nested
  class CursorMode {

    @Test
    void ofCursorValidParams() {
      PageRequest req = PageRequest.ofCursor("abc123", 25);
      assertThat(req.cursor()).isEqualTo("abc123");
      assertThat(req.limit()).isEqualTo(25);
      assertThat(req.offset()).isZero();
      assertThat(req.isCursorMode()).isTrue();
    }

    @Test
    void ofCursorEmptyCursorIsNotCursorMode() {
      PageRequest req = PageRequest.ofCursor("", 25);
      assertThat(req.isCursorMode()).isFalse();
    }

    @Test
    void ofCursorNullCursorRejected() {
      assertThatThrownBy(() -> PageRequest.ofCursor(null, 25))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    void ofCursorInvalidLimitRejected() {
      assertThatThrownBy(() -> PageRequest.ofCursor("abc", 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("limit 必须在");
    }
  }

  @Nested
  class OfLimit {

    @Test
    void ofLimitSetsOffsetZero() {
      PageRequest req = PageRequest.ofLimit(100);
      assertThat(req.offset()).isZero();
      assertThat(req.limit()).isEqualTo(100);
    }
  }

  @Test
  void equalsAndHashCode() {
    PageRequest a = PageRequest.ofOffset(10, 25);
    PageRequest b = PageRequest.ofOffset(10, 25);
    assertThat(a).isEqualTo(b);
    assertThat(a.hashCode()).isEqualTo(b.hashCode());
  }

  @Test
  void notEqualDifferentOffset() {
    assertThat(PageRequest.ofOffset(10, 25)).isNotEqualTo(PageRequest.ofOffset(20, 25));
  }

  @Test
  void notEqualDifferentLimit() {
    assertThat(PageRequest.ofOffset(10, 25)).isNotEqualTo(PageRequest.ofOffset(10, 50));
  }

  @Test
  void notEqualDifferentCursor() {
    assertThat(PageRequest.ofCursor("a", 25)).isNotEqualTo(PageRequest.ofCursor("b", 25));
  }

  @Test
  void toStringContainsOffset() {
    assertThat(PageRequest.ofOffset(10, 25).toString()).contains("offset=10").contains("limit=25");
  }

  @Test
  void toStringContainsCursor() {
    assertThat(PageRequest.ofCursor("abc", 25).toString())
        .contains("cursor=abc")
        .contains("limit=25");
  }
}
