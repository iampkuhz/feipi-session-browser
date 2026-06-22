package com.feipi.session.browser.contracttest.sourceSpi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.BoundedStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link BoundedStream} 契约测试。
 *
 * <p>验证有界确定性流的排序确定性、大小上限和不可变语义。
 */
@DisplayName("Source SPI — BoundedStream 契约")
class BoundedStreamContractTest {

  @Test
  @DisplayName("空流创建合法")
  void emptyStream() {
    BoundedStream<String> stream = BoundedStream.of(List.of(), 10, Optional.empty());
    assertThat(stream.isEmpty()).isTrue();
    assertThat(stream.size()).isZero();
    assertThat(stream.orderedItems()).isEmpty();
  }

  @Test
  @DisplayName("无排序器时保持原始顺序")
  void preservesOriginalOrderWithoutComparator() {
    List<String> items = List.of("c", "a", "b");
    BoundedStream<String> stream = BoundedStream.of(items, 10, Optional.empty());
    assertThat(stream.orderedItems()).containsExactly("c", "a", "b");
  }

  @Test
  @DisplayName("有排序器时产生确定性排序")
  void deterministicOrderWithComparator() {
    List<String> items = List.of("c", "a", "b");
    BoundedStream<String> stream =
        BoundedStream.of(items, 10, Optional.of(Comparator.naturalOrder()));
    assertThat(stream.orderedItems()).containsExactly("a", "b", "c");
  }

  @Test
  @DisplayName("超过上限时截断")
  void truncatesWhenExceedingMaxSize() {
    List<String> items = List.of("a", "b", "c", "d", "e");
    BoundedStream<String> stream =
        BoundedStream.of(items, 3, Optional.of(Comparator.naturalOrder()));
    assertThat(stream.size()).isEqualTo(3);
    assertThat(stream.orderedItems()).containsExactly("a", "b", "c");
  }

  @Test
  @DisplayName("orderedItems 返回不可变列表")
  void orderedItemsImmutable() {
    BoundedStream<String> stream = BoundedStream.of(List.of("a"), 10, Optional.empty());
    assertThatThrownBy(() -> stream.orderedItems().add("b"))
        .isInstanceOf(UnsupportedOperationException.class);
  }

  @Test
  @DisplayName("多次调用 orderedItems 返回相同结果")
  void deterministicRepeatedAccess() {
    List<Integer> items = List.of(3, 1, 4, 1, 5);
    BoundedStream<Integer> stream =
        BoundedStream.of(items, 10, Optional.of(Comparator.naturalOrder()));
    List<Integer> first = stream.orderedItems();
    List<Integer> second = stream.orderedItems();
    assertThat(first).isEqualTo(second);
  }

  @Test
  @DisplayName("stream() 产生相同顺序的元素")
  void streamMatchesOrderedItems() {
    List<String> items = List.of("z", "a", "m");
    BoundedStream<String> stream =
        BoundedStream.of(items, 10, Optional.of(Comparator.naturalOrder()));
    assertThat(stream.stream().toList()).containsExactly("a", "m", "z");
  }

  @Test
  @DisplayName("forEach 按确定性顺序执行")
  void forEachInDeterministicOrder() {
    List<Integer> items = List.of(3, 1, 2);
    BoundedStream<Integer> stream =
        BoundedStream.of(items, 10, Optional.of(Comparator.naturalOrder()));
    List<Integer> collected = new ArrayList<>();
    stream.forEach(collected::add);
    assertThat(collected).containsExactly(1, 2, 3);
  }

  @Test
  @DisplayName("负 maxSize 抛出 IllegalArgumentException")
  void negativeMaxSizeRejected() {
    assertThatThrownBy(() -> BoundedStream.of(List.of(), -1, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("comparator() 返回传入的排序器")
  void comparatorReturnsProvided() {
    Comparator<String> comp = Comparator.reverseOrder();
    BoundedStream<String> stream = BoundedStream.of(List.of("a"), 10, Optional.of(comp));
    assertThat(stream.comparator()).contains(comp);
  }

  @Test
  @DisplayName("无排序器时 comparator() 返回空")
  void emptyComparatorWhenNoneProvided() {
    BoundedStream<String> stream = BoundedStream.of(List.of("a"), 10, Optional.empty());
    assertThat(stream.comparator()).isEmpty();
  }
}
