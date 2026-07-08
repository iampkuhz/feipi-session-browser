package com.feipi.session.browser.common.validation;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 不可变集合防御性拷贝工具。 */
public final class ImmutableCopies {

  private ImmutableCopies() {}

  /**
   * 将可空集合复制为不可变列表，{@code null} 转为空列表。
   *
   * @param values 原始集合
   * @param <T> 元素类型
   * @return 不可变列表
   */
  public static <T> List<T> listOrEmpty(Collection<? extends T> values) {
    return values == null ? List.of() : List.copyOf(values);
  }

  /**
   * 将可空 map 复制为不可变 map，{@code null} 转为空 map。
   *
   * @param values 原始 map
   * @param <K> key 类型
   * @param <V> value 类型
   * @return 不可变 map
   */
  public static <K, V> Map<K, V> mapOrEmpty(Map<? extends K, ? extends V> values) {
    return values == null ? Map.of() : Map.copyOf(values);
  }

  /**
   * 将可空集合复制为不可变 set，{@code null} 转为空 set。
   *
   * @param values 原始集合
   * @param <T> 元素类型
   * @return 不可变 set
   */
  public static <T> Set<T> setOrEmpty(Collection<? extends T> values) {
    return values == null ? Set.of() : Set.copyOf(values);
  }

  /**
   * 将可空集合复制为不可变列表，并校验元素数量上限。
   *
   * @param values 原始集合
   * @param maxSize 最大元素数量
   * @param fieldName 字段名称
   * @param <T> 元素类型
   * @return 不可变列表
   * @throws IllegalArgumentException 当元素数量超过上限时
   */
  public static <T> List<T> boundedListOrEmpty(
      Collection<? extends T> values, int maxSize, String fieldName) {
    List<T> copy = listOrEmpty(values);
    checkSize(copy.size(), maxSize, fieldName);
    return copy;
  }

  /**
   * 将可空 map 复制为不可变 map，并校验元素数量上限。
   *
   * @param values 原始 map
   * @param maxSize 最大元素数量
   * @param fieldName 字段名称
   * @param <K> key 类型
   * @param <V> value 类型
   * @return 不可变 map
   * @throws IllegalArgumentException 当元素数量超过上限时
   */
  public static <K, V> Map<K, V> boundedMapOrEmpty(
      Map<? extends K, ? extends V> values, int maxSize, String fieldName) {
    Map<K, V> copy = mapOrEmpty(values);
    checkSize(copy.size(), maxSize, fieldName);
    return copy;
  }

  /**
   * 将可空集合复制为不可变 set，并校验元素数量上限。
   *
   * @param values 原始集合
   * @param maxSize 最大元素数量
   * @param fieldName 字段名称
   * @param <T> 元素类型
   * @return 不可变 set
   * @throws IllegalArgumentException 当元素数量超过上限时
   */
  public static <T> Set<T> boundedSetOrEmpty(
      Collection<? extends T> values, int maxSize, String fieldName) {
    Set<T> copy = setOrEmpty(values);
    checkSize(copy.size(), maxSize, fieldName);
    return copy;
  }

  private static void checkSize(int actualSize, int maxSize, String fieldName) {
    if (actualSize > maxSize) {
      throw new IllegalArgumentException(fieldName + " size exceeds limit " + maxSize);
    }
  }
}
