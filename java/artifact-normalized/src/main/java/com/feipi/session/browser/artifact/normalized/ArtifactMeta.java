package com.feipi.session.browser.artifact.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Map;
import java.util.Objects;

/**
 * 归一化制品元数据。
 *
 * <p>记录制品的 schema 版本、生成器、内容哈希、内容大小、生成时间戳以及源指纹映射。 元数据与数据文件分离存储，作为写入的最后一步提交， 确保中间状态不会被识别为有效制品。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有字段不得为 null。
 *   <li>{@code contentSize} 必须非负。
 *   <li>{@code sourceFingerprints} 使用不可变副本。
 * </ul>
 *
 * @param schemaVersion 归一化 schema 版本号，来自 {@code NormalizedConstants}
 * @param generator 生成器标识
 * @param contentHash 数据文件内容的 SHA-256 十六进制摘要
 * @param contentSize 数据文件内容的字节长度
 * @param generatedAt 生成时间戳，ISO-8601 格式 UTC
 * @param sourceFingerprints 源路径到内容哈希的映射
 */
@DomainModel
public record ArtifactMeta(
    @CoreField String schemaVersion,
    @CoreField String generator,
    @CoreField String contentHash,
    @CoreField long contentSize,
    @CoreField String generatedAt,
    @CoreField Map<String, String> sourceFingerprints) {

  /**
   * 紧凑构造器，验证非空约束并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 {@code contentSize} 为负数时
   */
  public ArtifactMeta {
    Objects.requireNonNull(schemaVersion, "schemaVersion 不得为 null");
    Objects.requireNonNull(generator, "generator 不得为 null");
    Objects.requireNonNull(contentHash, "contentHash 不得为 null");
    if (contentSize < 0) {
      throw new IllegalArgumentException("contentSize 不得为负数; got " + contentSize);
    }
    Objects.requireNonNull(generatedAt, "generatedAt 不得为 null");
    sourceFingerprints = sourceFingerprints == null ? Map.of() : Map.copyOf(sourceFingerprints);
  }
}
