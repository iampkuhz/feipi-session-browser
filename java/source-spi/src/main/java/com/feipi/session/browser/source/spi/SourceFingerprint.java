package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Objects;
import java.util.Optional;

/**
 * 会话源文件指纹。
 *
 * <p>标识一个物理源文件的唯一性证据。mtime 不是唯一一致性证据； 当 {@code contentHash} 存在时，调用方应优先使用内容哈希判断文件是否变化。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code path} 不得为空。
 *   <li>{@code sourceId} 不得为 null。
 *   <li>{@code sizeBytes} 非负。
 *   <li>{@code lastModifiedMs} 非负。
 * </ul>
 *
 * @param path 源文件的绝对路径字符串
 * @param sourceId 所属源适配器标识
 * @param sizeBytes 文件大小（字节）
 * @param lastModifiedMs 最后修改时间（毫秒时间戳）
 * @param contentHash 内容哈希值，{@code Absent} 表示未计算
 */
@DomainModel
public record SourceFingerprint(
    @CoreField String path,
    @CoreField SourceId sourceId,
    @CoreField long sizeBytes,
    @CoreField long lastModifiedMs,
    @CoreField Optional<String> contentHash) {

  /**
   * 紧凑构造器，验证指纹不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当路径为空或数值字段为负时
   */
  public SourceFingerprint {
    Objects.requireNonNull(path, "path 不得为 null");
    if (path.isEmpty()) {
      throw new IllegalArgumentException("path 不得为空");
    }
    Objects.requireNonNull(sourceId, "sourceId 不得为 null");
    if (sizeBytes < 0) {
      throw new IllegalArgumentException("sizeBytes 不得为负: " + sizeBytes);
    }
    if (lastModifiedMs < 0) {
      throw new IllegalArgumentException("lastModifiedMs 不得为负: " + lastModifiedMs);
    }
    contentHash = contentHash == null ? Optional.empty() : contentHash;
    contentHash.ifPresent(
        hash -> {
          if (hash.isEmpty()) {
            throw new IllegalArgumentException("contentHash 不得为空字符串");
          }
        });
  }

  /**
   * 判断该指纹与另一指纹是否指向同一文件（仅比较路径和源标识）。
   *
   * @param other 另一个指纹
   * @return 路径和源标识相同时返回 {@code true}
   */
  public boolean sameFile(SourceFingerprint other) {
    if (other == null) {
      return false;
    }
    return path.equals(other.path) && sourceId == other.sourceId;
  }

  /**
   * 判断该指纹是否可能已过期（基于 mtime 和内容哈希双重检查）。
   *
   * <p>当内容哈希一致时，即使 mtime 变化也视为未过期。 当无内容哈希时，仅比较 mtime 和文件大小。
   *
   * @param other 另一个指纹，代表文件的当前状态
   * @return 指纹可能已过期时返回 {@code true}
   */
  public boolean isStaleComparedTo(SourceFingerprint other) {
    if (other == null) {
      return true;
    }
    if (!sameFile(other)) {
      return true;
    }
    // 如果两者都有内容哈希，优先比较哈希
    if (contentHash.isPresent() && other.contentHash.isPresent()) {
      return !contentHash.get().equals(other.contentHash.get());
    }
    // 回退到文件大小加修改时间比较
    return sizeBytes != other.sizeBytes || lastModifiedMs != other.lastModifiedMs;
  }
}
