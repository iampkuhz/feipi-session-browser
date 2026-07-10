package com.feipi.session.browser.scan.artifact;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.Map;

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
    /* 归一化 schema 版本号。 */
    @NotBlank @CoreField String schemaVersion,

    /* 生成器标识。 */
    @NotBlank @CoreField String generator,

    /* 数据文件内容的 SHA-256 十六进制摘要。 */
    @NotBlank @CoreField String contentHash,

    /* 数据文件内容的字节长度。 */
    @PositiveOrZero @CoreField long contentSize,

    /* 生成时间戳，ISO-8601 格式 UTC。 */
    @NotBlank @CoreField String generatedAt,

    /* 源路径到内容哈希的映射。 */
    @CoreField Map<String, String> sourceFingerprints) {

  /**
   * 紧凑构造器，验证非空约束并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 {@code contentSize} 为负数时
   */
  public ArtifactMeta {
    ValidationSupport.validateCanonicalConstructor(
        ArtifactMeta.class,
        schemaVersion,
        generator,
        contentHash,
        contentSize,
        generatedAt,
        sourceFingerprints);
    sourceFingerprints = ImmutableCopies.mapOrEmpty(sourceFingerprints);
  }
}
