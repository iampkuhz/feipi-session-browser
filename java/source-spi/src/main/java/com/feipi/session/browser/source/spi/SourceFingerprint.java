package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.Optional;

/**
 * 会话源文件指纹。
 *
 * <p>标识一个物理源文件的唯一性证据。mtime 不是唯一一致性证据； 当 {@code contentHash} 存在时，调用方应优先使用内容哈希判断文件是否变化。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code locator} 不得为空，应为相对路径或稳定标识，不得使用绝对 home 路径作为持久身份。
 *   <li>{@code sourceId} 不得为 null。
 *   <li>{@code sizeBytes} 非负。
 *   <li>{@code lastModifiedMs} 非负。
 * </ul>
 *
 * @param locator 源文件的稳定标识（相对路径或逻辑定位），不得为绝对 home 路径
 * @param sourceId 所属源适配器标识，不得为 null
 * @param sizeBytes 文件大小（字节），非负
 * @param lastModifiedMs 最后修改时间（毫秒时间戳），非负
 * @param contentHash 内容哈希值，{@code Absent} 表示未计算；若存在则不得为空字符串
 * @param hashAlgorithm 内容哈希算法名称（如 {@code "SHA-256"}），{@code empty} 表示未指定；若存在则不得为空字符串
 */
@DomainModel
public record SourceFingerprint(
    /* 源文件的稳定标识（相对路径或逻辑定位），不得为绝对 home 路径。 */
    @NotNull @NotBlank @CoreField String locator,

    /* 所属源适配器标识，不得为 null。 */
    @NotNull @CoreField SourceId sourceId,

    /* 文件大小（字节），非负。 */
    @PositiveOrZero @CoreField long sizeBytes,

    /* 最后修改时间（毫秒时间戳），非负。 */
    @PositiveOrZero @CoreField long lastModifiedMs,

    /* 内容哈希值，Absent 表示未计算；若存在则不得为空字符串。 */
    @CoreField Optional<String> contentHash,

    /* 内容哈希算法名称（如 SHA-256），empty 表示未指定；若存在则不得为空字符串。 */
    @CoreField Optional<String> hashAlgorithm) {

  /**
   * 紧凑构造器，处理默认值并校验约束。
   *
   * @throws NullPointerException 当必填对象字段为 null 时
   * @throws IllegalArgumentException 当字符串为空或数值非法时
   */
  public SourceFingerprint {
    contentHash = contentHash == null ? Optional.empty() : contentHash;
    contentHash.ifPresent(
        hash -> {
          if (hash.isEmpty()) {
            throw new IllegalArgumentException("contentHash 不得为空字符串");
          }
        });
    hashAlgorithm = hashAlgorithm == null ? Optional.empty() : hashAlgorithm;
    hashAlgorithm.ifPresent(
        algo -> {
          if (algo.isEmpty()) {
            throw new IllegalArgumentException("hashAlgorithm 不得为空字符串");
          }
        });
    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceFingerprint.class,
          locator,
          sourceId,
          sizeBytes,
          lastModifiedMs,
          contentHash,
          hashAlgorithm);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 判断该指纹与另一指纹是否指向同一文件（仅比较 locator 和源标识）。
   *
   * @param other 另一个指纹
   * @return locator 和源标识相同时返回 {@code true}
   */
  public boolean sameFile(SourceFingerprint other) {
    if (other == null) {
      return false;
    }
    return locator.equals(other.locator) && sourceId == other.sourceId;
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

  private static void translateValidation(ConstraintViolationException e) {
    var violations = e.getConstraintViolations();
    for (var v : violations) {
      String rawPath = v.getPropertyPath().toString();
      String field =
          rawPath.contains(".") ? rawPath.substring(rawPath.lastIndexOf('.') + 1) : rawPath;
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
      if (type == NotBlank.class) {
        if (v.getInvalidValue() == null) {
          throw new NullPointerException(field + " 不得为 null");
        }
        throw new IllegalArgumentException(field + " 不得为空");
      }
      if (type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
