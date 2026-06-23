package com.feipi.session.browser.reuse.analyzer.cache;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.TreeMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** AnalyzerCache 测试。 验证缓存 key 构建、存取、失效和清除。 */
class AnalyzerCacheTest {

  @TempDir Path tempDir;

  private AnalyzerCache cache;

  @BeforeEach
  void setup() {
    cache = new AnalyzerCache(tempDir.resolve("cache"));
  }

  @Test
  void buildCacheKeyDeterministic() {
    String key1 = AnalyzerCache.buildCacheKey("src1", "spoon1", "policy1", 25, "topo1", "cp1");
    String key2 = AnalyzerCache.buildCacheKey("src1", "spoon1", "policy1", 25, "topo1", "cp1");
    assertThat(key1).isEqualTo(key2);
    assertThat(key1).hasSize(64).matches("[0-9a-f]{64}");
  }

  @Test
  void buildCacheKeyDifferentInputsDifferentKey() {
    String key1 = AnalyzerCache.buildCacheKey("src1", "spoon1", "policy1", 25, "topo1", "cp1");
    String key2 = AnalyzerCache.buildCacheKey("src2", "spoon1", "policy1", 25, "topo1", "cp1");
    assertThat(key1).isNotEqualTo(key2);
  }

  @Test
  void storeAndLoadRoundTrip() throws IOException {
    String cacheKey = "test-key-123";
    Map<String, Object> data = new TreeMap<>();
    data.put("status", "PASS");
    data.put("findings", java.util.List.of());

    cache.store(cacheKey, data);

    Map<String, Object> loaded = cache.load(cacheKey);
    assertThat(loaded).isNotNull();
    assertThat(loaded.get("status")).isEqualTo("PASS");
    assertThat(loaded.get("cacheKey")).isEqualTo(cacheKey);
  }

  @Test
  void loadNonExistentKeyReturnsNull() throws IOException {
    Map<String, Object> result = cache.load("non-existent-key");
    assertThat(result).isNull();
  }

  @Test
  void isValidExistingCacheReturnsTrue() throws IOException {
    String cacheKey = "valid-key";
    cache.store(cacheKey, Map.of("status", "PASS"));
    assertThat(cache.isValid(cacheKey)).isTrue();
  }

  @Test
  void isValidNonExistentReturnsFalse() {
    assertThat(cache.isValid("missing-key")).isFalse();
  }

  @Test
  void clearRemovesAllCacheFiles() throws IOException {
    cache.store("key1", Map.of("data", "a"));
    cache.store("key2", Map.of("data", "b"));

    assertThat(cache.isValid("key1")).isTrue();
    assertThat(cache.isValid("key2")).isTrue();

    cache.clear();

    assertThat(cache.isValid("key1")).isFalse();
    assertThat(cache.isValid("key2")).isFalse();
  }

  @Test
  void cacheDirectoryCreatedOnStore() throws IOException {
    Path cacheDir = tempDir.resolve("new-cache");
    AnalyzerCache newCache = new AnalyzerCache(cacheDir);

    assertThat(Files.exists(cacheDir)).isFalse();

    newCache.store("key", Map.of("data", "test"));

    assertThat(Files.exists(cacheDir)).isTrue();
  }
}
