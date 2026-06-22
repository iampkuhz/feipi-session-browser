package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

/**
 * 调用级别的源单元引用范围。
 *
 * <p>建模调用对目录源单元或命名源单元序列的引用，避免重复携带载荷内容。 范围索引必须非负，并保持适配器提供的命名序列顺序。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code start} 和 {@code end} 必须非负，{@code end >= start}。
 *   <li>{@code refs} 使用不可变副本。
 *   <li>{@code sequence} 和 {@code role} 使用 {@code Optional} 区分空值。
 * </ul>
 *
 * @param sequence 可选的源单元序列名称
 * @param start 包含起始索引
 * @param end 排除结束索引
 * @param refs 调用显式引用的目录单元键列表
 * @param role 可选的适配器分配显示角色
 */
@DomainModel
public record SourceUnitRefRange(
    Optional<String> sequence,
    @CoreField int start,
    @CoreField int end,
    List<String> refs,
    Optional<String> role) {

  /**
   * 紧凑构造器，验证范围不变量并执行防御性拷贝。
   *
   * @throws IllegalArgumentException 当索引为负数或 {@code end} 小于 {@code start} 时
   */
  public SourceUnitRefRange {
    if (start < 0) {
      throw new IllegalArgumentException(
          "source_unit_ref_range.start must be non-negative; got " + start);
    }
    if (end < 0) {
      throw new IllegalArgumentException(
          "source_unit_ref_range.end must be non-negative; got " + end);
    }
    if (end < start) {
      throw new IllegalArgumentException(
          "source_unit_ref_range.end must be >= start; start=" + start + ", end=" + end);
    }
    List<String> copy = refs == null ? Collections.emptyList() : List.copyOf(refs);
    if (copy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "refs size " + copy.size() + " exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    refs = copy;
    sequence = sequence == null ? Optional.empty() : sequence;
    role = role == null ? Optional.empty() : role;
  }
}
