package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
    @CoreField String unitKey,
    @CoreField String originPath,
    @CoreField String canonicalSourceLocator,
    @CoreField String unitType,
    @CoreField String candidate,
    @CoreField SourceUnitDirection direction,
    @CoreField int eventOrder,
    @CoreField int partIndex,
    @CoreField ByteRange byteRange,
    @CoreField String contentHash,
    Optional<String> timestamp,
    Optional<String> label,
    int priority,
    Optional<String> preview,
    Optional<String> text,
    Object payload,
    Optional<String> subSource,
    Optional<String> sourceCandidate,
    List<Map<String, Object>> diagnostics) {

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当排序字段为负数或集合超限时
   */
  public SourceUnitCatalogEntry {
    Objects.requireNonNull(unitKey, "unitKey 不得为 null");
    Objects.requireNonNull(originPath, "originPath 不得为 null");
    Objects.requireNonNull(canonicalSourceLocator, "canonicalSourceLocator 不得为 null");
    Objects.requireNonNull(unitType, "unitType 不得为 null");
    Objects.requireNonNull(candidate, "candidate 不得为 null");
    Objects.requireNonNull(direction, "direction 不得为 null");
    Objects.requireNonNull(byteRange, "byteRange 不得为 null");
    Objects.requireNonNull(contentHash, "contentHash 不得为 null");

    if (eventOrder < 0) {
      throw new IllegalArgumentException(
          "source_unit.eventOrder must be non-negative; got " + eventOrder);
    }
    if (partIndex < 0) {
      throw new IllegalArgumentException(
          "source_unit.partIndex must be non-negative; got " + partIndex);
    }
    if (priority < 0) {
      throw new IllegalArgumentException(
          "source_unit.priority must be non-negative; got " + priority);
    }

    // Optional 字段规范化
    timestamp = timestamp == null ? Optional.empty() : timestamp;
    label = label == null ? Optional.empty() : label;
    preview = preview == null ? Optional.empty() : preview;
    text = text == null ? Optional.empty() : text;
    subSource = subSource == null ? Optional.empty() : subSource;
    sourceCandidate = sourceCandidate == null ? Optional.empty() : sourceCandidate;

    // 诊断信息防御性拷贝
    List<Map<String, Object>> diagCopy =
        diagnostics == null ? Collections.emptyList() : List.copyOf(diagnostics);
    if (diagCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "diagnostics size "
              + diagCopy.size()
              + " exceeds limit "
              + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    diagnostics = diagCopy;
  }
}
