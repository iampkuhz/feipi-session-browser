package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 与调用无关的源单元目录条目。
 *
 * <p>建模归因源内容的可见目录条目。适配器在归一化阶段填充目录， 制品验证器将条目水合为不可变记录。目录键、方向、事件顺序、字节范围和内容哈希 构成稳定的溯源合约，被 UI 归因功能消费。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code unitKey}、{@code originPath}、{@code canonicalSourceLocator}、 {@code unitType}、{@code
 *       candidate}、{@code contentHash} 不得为 null。
 *   <li>{@code direction} 必须为合法值（request/response）。
 *   <li>{@code eventOrder}、{@code partIndex} 必须非负。
 *   <li>{@code priority} 必须非负，默认值 50。
 *   <li>{@code byteRange} 不得为 null。
 *   <li>{@code diagnostics} 使用不可变副本，大小不超过上限。
 *   <li>{@code payload} 为 {@code Object} 类型，记录不可变快照。
 * </ul>
 *
 * @param unitKey 稳定的单元键，供调用和序列引用
 * @param originPath 产生该单元的源文件路径
 * @param canonicalSourceLocator 适配器特定的源跨度定位符
 * @param unitType 目录中存储的源单元类别
 * @param candidate 归因候选桶，用于 UI 分组
 * @param direction 会话的请求侧或响应侧
 * @param eventOrder 源转录中的非负事件顺序
 * @param partIndex 源事件内的非负索引
 * @param byteRange 源载荷内的字节偏移
 * @param contentHash 用于去重的稳定内容哈希
 * @param timestamp 可选的关联源时间戳
 * @param label 可选的显示标签
 * @param priority 归因显示排名的非负优先级
 * @param preview 可选的短预览文本
 * @param text 可选的完整文本（安全持久化时）
 * @param payload 可选的 provider 载荷片段
 * @param subSource 可选的嵌套源标签
 * @param sourceCandidate 可选的归一化前原始候选标签
 * @param diagnostics 关联的适配器诊断信息列表，不可变
 */
@DomainModel
public record SourceUnitCatalogEntry(
    /* 稳定的单元键，供调用和序列引用。 */
    @NotBlank @CoreField String unitKey,

    /* 产生该单元的源文件路径。 */
    @NotBlank @CoreField String originPath,

    /* 适配器特定的源跨度定位符。 */
    @NotBlank @CoreField String canonicalSourceLocator,

    /* 目录中存储的源单元类别。 */
    @NotBlank @CoreField String unitType,

    /* 归因候选桶，用于 UI 分组。 */
    @NotNull @CoreField String candidate,

    /* 会话的请求侧或响应侧。 */
    @NotNull @CoreField SourceUnitDirection direction,

    /* 源转录中的非负事件顺序。 */
    @PositiveOrZero @CoreField int eventOrder,

    /* 源事件内的非负索引。 */
    @PositiveOrZero @CoreField int partIndex,

    /* 源载荷内的字节偏移。 */
    @NotNull @CoreField ByteRange byteRange,

    /* 用于去重的稳定内容哈希。 */
    @NotNull @CoreField String contentHash,

    /* 可选的关联源时间戳。 */
    Optional<String> timestamp,

    /* 可选的显示标签。 */
    Optional<String> label,

    /* 归因显示排名的非负优先级。 */
    @PositiveOrZero int priority,

    /* 可选的短预览文本。 */
    Optional<String> preview,

    /* 可选的完整文本（安全持久化时）。 */
    Optional<String> text,

    /* 可选的 provider 载荷片段。 */
    Object payload,

    /* 可选的嵌套源标签。 */
    Optional<String> subSource,

    /* 可选的归一化前原始候选标签。 */
    Optional<String> sourceCandidate,

    /* 关联的适配器诊断信息列表，不可变。 */
    List<Map<String, Object>> diagnostics) {

  /**
   * 紧凑构造器，处理默认值并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当排序字段为负数或集合超限时
   */
  public SourceUnitCatalogEntry {
    // Optional 字段规范化
    timestamp = timestamp == null ? Optional.empty() : timestamp;
    label = label == null ? Optional.empty() : label;
    preview = preview == null ? Optional.empty() : preview;
    text = text == null ? Optional.empty() : text;
    subSource = subSource == null ? Optional.empty() : subSource;
    sourceCandidate = sourceCandidate == null ? Optional.empty() : sourceCandidate;

    // 诊断信息防御性拷贝
    diagnostics =
        ImmutableCopies.boundedListOrEmpty(
            diagnostics, NormalizedConstants.MAX_COLLECTION_SIZE, "diagnostics");

    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceUnitCatalogEntry.class,
          unitKey,
          originPath,
          canonicalSourceLocator,
          unitType,
          candidate,
          direction,
          eventOrder,
          partIndex,
          byteRange,
          contentHash,
          timestamp,
          label,
          priority,
          preview,
          text,
          payload,
          subSource,
          sourceCandidate,
          diagnostics);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 将 Jakarta 校验违规翻译为向后兼容的异常类型。
   *
   * @param e 原始校验违规异常
   */
  private static void translateValidation(ConstraintViolationException e) {
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
    }
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
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
