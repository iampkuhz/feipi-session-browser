package com.feipi.session.browser.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * QueryCache 单元测试。
 *
 * <p>验证有界缓存的容量限制、LRU 淘汰和失效语义。
 */
@DisplayName("QueryCache 测试")
class QueryCacheTest {

  @Nested
  @DisplayName("基本缓存语义")
  class BasicCacheSemantics {

    @Test
    @DisplayName("getOrLoad 缓存未命中时调用 loader")
    void cacheMissCallsLoader() {
      QueryCache cache = new QueryCache(10);
      int[] callCount = {0};
      String result =
          cache.getOrLoad(
              "test",
              1,
              1,
              () -> {
                callCount[0]++;
                return "value";
              });
      assertThat(result).isEqualTo("value");
      assertThat(callCount[0]).isEqualTo(1);
    }

    @Test
    @DisplayName("相同键命中缓存，不调用 loader")
    void cacheHitSkipsLoader() {
      QueryCache cache = new QueryCache(10);
      int[] callCount = {0};
      cache.getOrLoad(
          "test",
          1,
          1,
          () -> {
            callCount[0]++;
            return "value";
          });
      String result =
          cache.getOrLoad(
              "test",
              1,
              1,
              () -> {
                callCount[0]++;
                return "other";
              });
      assertThat(result).isEqualTo("value");
      assertThat(callCount[0]).isEqualTo(1);
    }

    @Test
    @DisplayName("不同参数哈希产生不同缓存条目")
    void differentParamsDifferentEntries() {
      QueryCache cache = new QueryCache(10);
      String r1 = cache.getOrLoad("q", 1, 1, () -> "value1");
      String r2 = cache.getOrLoad("q", 2, 1, () -> "value2");
      assertThat(r1).isEqualTo("value1");
      assertThat(r2).isEqualTo("value2");
      assertThat(cache.size()).isEqualTo(2);
    }

    @Test
    @DisplayName("不同 schema 版本产生不同缓存条目")
    void differentSchemaVersionDifferentEntries() {
      QueryCache cache = new QueryCache(10);
      String r1 = cache.getOrLoad("q", 1, 1, () -> "v1");
      String r2 = cache.getOrLoad("q", 1, 2, () -> "v2");
      assertThat(r1).isEqualTo("v1");
      assertThat(r2).isEqualTo("v2");
    }
  }

  @Nested
  @DisplayName("有界容量与 LRU 淘汰")
  class BoundedCapacity {

    @Test
    @DisplayName("超过 maxSize 时淘汰最旧条目")
    void lruEviction() {
      QueryCache cache = new QueryCache(2);
      cache.getOrLoad("a", 0, 1, () -> "A");
      cache.getOrLoad("b", 0, 1, () -> "B");
      assertThat(cache.size()).isEqualTo(2);

      // 插入第三个，淘汰最旧的 "a"
      cache.getOrLoad("c", 0, 1, () -> "C");
      assertThat(cache.size()).isEqualTo(2);

      // "a" 已被淘汰，重新加载
      int[] callCount = {0};
      cache.getOrLoad(
          "a",
          0,
          1,
          () -> {
            callCount[0]++;
            return "A-new";
          });
      assertThat(callCount[0]).isEqualTo(1);
    }

    @Test
    @DisplayName("LRU 访问顺序更新：最近访问的条目不被淘汰")
    void lruAccessOrderUpdate() {
      QueryCache cache = new QueryCache(2);
      cache.getOrLoad("a", 0, 1, () -> "A");
      cache.getOrLoad("b", 0, 1, () -> "B");

      // 访问 "a"，更新 LRU 顺序
      cache.getOrLoad("a", 0, 1, () -> "A-new");

      // 插入 "c"，应淘汰 "b"（最少最近使用）
      cache.getOrLoad("c", 0, 1, () -> "C");
      assertThat(cache.size()).isEqualTo(2);

      // "b" 被淘汰
      int[] callCount = {0};
      cache.getOrLoad(
          "b",
          0,
          1,
          () -> {
            callCount[0]++;
            return "B-new";
          });
      assertThat(callCount[0]).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("失效语义")
  class InvalidationSemantics {

    @Test
    @DisplayName("invalidateAll 清空缓存")
    void invalidateAllClearsCache() {
      QueryCache cache = new QueryCache(10);
      cache.getOrLoad("a", 0, 1, () -> "A");
      cache.getOrLoad("b", 0, 1, () -> "B");
      assertThat(cache.size()).isEqualTo(2);

      cache.invalidateAll();
      assertThat(cache.size()).isZero();
    }

    @Test
    @DisplayName("失效后相同键重新加载")
    void reloadAfterInvalidation() {
      QueryCache cache = new QueryCache(10);
      cache.getOrLoad("test", 1, 1, () -> "old");

      cache.invalidateAll();

      int[] callCount = {0};
      String result =
          cache.getOrLoad(
              "test",
              1,
              1,
              () -> {
                callCount[0]++;
                return "new";
              });
      assertThat(result).isEqualTo("new");
      assertThat(callCount[0]).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("构造器验证")
  class ConstructorValidation {

    @Test
    @DisplayName("maxSize 为 0 时抛出异常")
    void zeroMaxSizeThrows() {
      assertThatThrownBy(() -> new QueryCache(0)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("maxSize 为负时抛出异常")
    void negativeMaxSizeThrows() {
      assertThatThrownBy(() -> new QueryCache(-1)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("withDefaultSize 创建 64 容量缓存")
    void defaultSizeIs64() {
      QueryCache cache = QueryCache.withDefaultSize();
      assertThat(cache.maxSize()).isEqualTo(64);
    }
  }
}
