package com.feipi.session.browser.reuse.analyzer.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Map;
import java.util.TreeMap;

/**
 * 持久化本地缓存。 缓存位于 .gradle/feipi-reuse-analysis/，不提交到版本控制。
 *
 * <p>Cache key 包含： source SHA-256、Spoon version、analyzer version、policy version、 Java level、module
 * topology、compile classpath digest。
 *
 * <p>Cache miss/invalid 时全量重建。
 */
public final class AnalyzerCache {

  /** Analyzer 自身的版本号，用于 cache key。 */
  public static final String ANALYZER_VERSION = "0.1.0";

  private final Path cacheDirectory;
  private final ObjectMapper objectMapper;

  /** 创建缓存实例。 */
  public AnalyzerCache(Path cacheDirectory) {
    this.cacheDirectory = cacheDirectory;
    this.objectMapper = new ObjectMapper();
  }

  /** 构造 cache key。 包含所有影响缓存有效性的因素。 */
  public static String buildCacheKey(
      String sourceSha256,
      String spoonVersion,
      String policyVersion,
      int javaLevel,
      String moduleTopologyDigest,
      String classpathDigest) {
    StringBuilder sb = new StringBuilder();
    sb.append("src=").append(sourceSha256);
    sb.append("|spoon=").append(spoonVersion);
    sb.append("|analyzer=").append(ANALYZER_VERSION);
    sb.append("|policy=").append(policyVersion);
    sb.append("|java=").append(javaLevel);
    sb.append("|topology=").append(moduleTopologyDigest);
    sb.append("|classpath=").append(classpathDigest);
    return sha256(sb.toString());
  }

  /** 从缓存加载索引数据。 如果缓存不存在或 key 不匹配，返回 null。 */
  public Map<String, Object> load(String cacheKey) throws IOException {
    Path cacheFile = cacheDirectory.resolve("index-" + cacheKey + ".json");
    if (!Files.exists(cacheFile)) {
      return null;
    }
    try {
      @SuppressWarnings("unchecked")
      Map<String, Object> data =
          objectMapper.readValue(Files.readString(cacheFile, StandardCharsets.UTF_8), Map.class);
      // 验证 key 匹配
      Object storedKey = data.get("cacheKey");
      if (!cacheKey.equals(storedKey)) {
        return null; // key 不匹配，缓存失效
      }
      return data;
    } catch (IOException e) {
      // 缓存损坏，返回 null 触发重建
      return null;
    }
  }

  /** 将索引数据存入缓存。 */
  public void store(String cacheKey, Map<String, Object> indexData) throws IOException {
    Files.createDirectories(cacheDirectory);
    Map<String, Object> cacheEntry = new TreeMap<>(indexData);
    cacheEntry.put("cacheKey", cacheKey);
    cacheEntry.put("cachedAt", System.currentTimeMillis());
    Path cacheFile = cacheDirectory.resolve("index-" + cacheKey + ".json");
    Files.writeString(
        cacheFile,
        objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(cacheEntry),
        StandardCharsets.UTF_8);
  }

  /** 检查缓存是否有效（key 存在且可读）。 */
  public boolean isValid(String cacheKey) {
    try {
      return load(cacheKey) != null;
    } catch (IOException e) {
      return false;
    }
  }

  /** 清除所有缓存。 */
  public void clear() throws IOException {
    if (Files.exists(cacheDirectory)) {
      try (var stream = Files.list(cacheDirectory)) {
        for (Path file : stream.toList()) {
          if (file.getFileName().toString().startsWith("index-")) {
            Files.deleteIfExists(file);
          }
        }
      }
    }
  }

  /** 获取缓存目录路径。 */
  public Path cacheDirectory() {
    return cacheDirectory;
  }

  private static String sha256(String input) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
      StringBuilder sb = new StringBuilder(hash.length * 2);
      for (byte b : hash) {
        sb.append(String.format("%02x", b));
      }
      return sb.toString();
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 not available", e);
    }
  }
}
