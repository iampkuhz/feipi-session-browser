package com.feipi.session.browser.application;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * 有界只读查询缓存。
 *
 * <p>缓存昂贵的纯查询结果，键包含 schema 版本和失效令牌，保证 index 变更或 scan 后缓存自动失效。
 *
 * <p>设计约束：
 *
 * <ul>
 *   <li>有界容量，LRU 淘汰。
 *   <li>无 static mutable state，每个实例独立。
 *   <li>键包含 schema 版本和失效令牌，mutation/scan 后显式失效。
 * </ul>
 *
 * <p>校验放置：缓存不验证查询参数，信任 use case 传入的已验证类型。
 */
public final class QueryCache {

  private final int maxSize;
  private final Map<String, CacheEntry> cache;
  private final ReentrantReadWriteLock lock;
  private volatile long invalidationToken;

  /**
   * 创建指定容量的缓存。
   *
   * @param maxSize 最大缓存条目数，必须大于 0
   */
  public QueryCache(int maxSize) {
    if (maxSize <= 0) {
      throw new IllegalArgumentException("maxSize 必须大于 0; got " + maxSize);
    }
    this.maxSize = maxSize;
    this.lock = new ReentrantReadWriteLock();
    this.invalidationToken = 0L;
    this.cache =
        new LinkedHashMap<>(16, 0.75f, true) {
          @Override
          protected boolean removeEldestEntry(Map.Entry<String, CacheEntry> eldest) {
            return size() > maxSize;
          }
        };
  }

  /**
   * 创建默认容量（64）的缓存。
   *
   * @return 新缓存实例
   */
  public static QueryCache withDefaultSize() {
    return new QueryCache(64);
  }

  /**
   * 获取或计算缓存值。
   *
   * <p>键包含查询名、参数哈希、schema 版本和失效令牌。相同键返回缓存值，否则调用 loader 并缓存结果。
   *
   * @param queryName 查询标识，如 "sessionList"
   * @param paramsHash 参数哈希，区分不同过滤条件
   * @param schemaVersion schema 版本号
   * @param loader 缓存未命中时的值加载器
   * @param <T> 缓存值类型
   * @return 缓存或新计算的值
   */
  public <T> T getOrLoad(
      String queryName, int paramsHash, int schemaVersion, java.util.function.Supplier<T> loader) {
    Objects.requireNonNull(queryName, "queryName 不得为 null");
    Objects.requireNonNull(loader, "loader 不得为 null");

    String key = buildKey(queryName, paramsHash, schemaVersion);

    // 先尝试读锁
    lock.readLock().lock();
    try {
      CacheEntry entry = cache.get(key);
      if (entry != null && entry.invalidationToken == this.invalidationToken) {
        @SuppressWarnings("unchecked")
        T value = (T) entry.value;
        return value;
      }
    } finally {
      lock.readLock().unlock();
    }

    // 缓存未命中，计算并写入
    lock.writeLock().lock();
    try {
      // 双重检查
      CacheEntry entry = cache.get(key);
      if (entry != null && entry.invalidationToken == this.invalidationToken) {
        @SuppressWarnings("unchecked")
        T value = (T) entry.value;
        return value;
      }

      T value = loader.get();
      cache.put(key, new CacheEntry(value, invalidationToken));
      return value;
    } finally {
      lock.writeLock().unlock();
    }
  }

  /**
   * 显式失效所有缓存。
   *
   * <p>mutation 或 scan 后调用，递增失效令牌使所有现有条目失效。
   */
  public void invalidateAll() {
    lock.writeLock().lock();
    try {
      invalidationToken++;
      cache.clear();
    } finally {
      lock.writeLock().unlock();
    }
  }

  /**
   * 获取当前缓存条目数。
   *
   * @return 条目数
   */
  public int size() {
    lock.readLock().lock();
    try {
      return cache.size();
    } finally {
      lock.readLock().unlock();
    }
  }

  /**
   * 获取最大容量。
   *
   * @return 最大条目数
   */
  public int maxSize() {
    return maxSize;
  }

  /** 构建缓存键。 */
  private String buildKey(String queryName, int paramsHash, int schemaVersion) {
    return queryName + ":" + paramsHash + ":v" + schemaVersion + ":t" + invalidationToken;
  }

  /** 缓存条目。 */
  private static final class CacheEntry {
    final Object value;
    final long invalidationToken;

    CacheEntry(Object value, long invalidationToken) {
      this.value = value;
      this.invalidationToken = invalidationToken;
    }
  }
}
