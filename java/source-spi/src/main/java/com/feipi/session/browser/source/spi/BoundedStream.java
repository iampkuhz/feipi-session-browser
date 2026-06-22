package com.feipi.session.browser.source.spi;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.function.Consumer;
import java.util.stream.Stream;

/**
 * 有界确定性流。
 *
 * <p>提供大小受限且排序确定化的元素流。用于源适配器返回候选项列表时
 * 保证消费方获得一致的顺序和大小上限。
 *
 * <p>该接口不可变、可重复消费。每次调用 {@link #stream()} 返回新的流实例。
 *
 * @param <T> 流中元素的类型
 */
public interface BoundedStream<T> {

  /**
   * 返回流中元素的确定排序列表。
   *
   * <p>每次调用返回相同的排序结果。返回列表为不可变副本。
   *
   * @return 按确定性排序的元素列表
   */
  List<T> orderedItems();

  /**
   * 返回新的流实例，元素顺序与 {@link #orderedItems()} 一致。
   *
   * @return 新流实例
   */
  default Stream<T> stream() {
    return orderedItems().stream();
  }

  /**
   * 返回流中的元素数量。
   *
   * @return 元素数量，不超过 {@link #maxSize()}
   */
  default int size() {
    return orderedItems().size();
  }

  /**
   * 返回流的大小上限。
   *
   * @return 大小上限
   */
  int maxSize();

  /**
   * 返回流是否为空。
   *
   * @return 无元素时返回 {@code true}
   */
  default boolean isEmpty() {
    return orderedItems().isEmpty();
  }

  /**
   * 对每个元素按确定性顺序执行指定操作。
   *
   * @param action 要执行的操作
   */
  default void forEach(Consumer<? super T> action) {
    orderedItems().forEach(action);
  }

  /**
   * 返回该流使用的排序器。
   *
   * @return 排序器，如果未指定排序则返回空
   */
  Optional<Comparator<T>> comparator();

  /**
   * 从列表创建有界确定性流。
   *
   * <p>列表按提供的排序器排序，如果排序器为空则保持原始顺序。
   * 元素数量超过上限时截断。
   *
   * @param items 元素列表
   * @param maxSize 大小上限
   * @param comparator 排序器，为空则保持原始顺序
   * @param <T> 元素类型
   * @return 新的有界确定性流
   * @throws IllegalArgumentException 当 maxSize 为负时
   */
  static <T> BoundedStream<T> of(List<T> items, int maxSize, Optional<Comparator<T>> comparator) {
    if (maxSize < 0) {
      throw new IllegalArgumentException("maxSize 不得为负: " + maxSize);
    }
    List<T> sorted;
    if (comparator.isPresent()) {
      sorted = items.stream().sorted(comparator.get()).toList();
    } else {
      sorted = List.copyOf(items);
    }
    List<T> bounded = sorted.size() > maxSize ? sorted.subList(0, maxSize) : sorted;
    List<T> immutable = List.copyOf(bounded);
    return new BoundedStream<>() {
      @Override
      public List<T> orderedItems() {
        return immutable;
      }

      @Override
      public int maxSize() {
        return maxSize;
      }

      @Override
      public Optional<Comparator<T>> comparator() {
        return comparator;
      }
    };
  }
}
