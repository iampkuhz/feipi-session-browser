package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 源内容字节偏移范围。
 *
 * <p>表示源单元在原始文件中的字节偏移区间，用于精确定位归因内容。
 * {@code start} 为包含起始偏移，{@code end} 为排除结束偏移。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code start} 和 {@code end} 必须非负。
 *   <li>{@code end} 必须大于等于 {@code start}。
 * </ul>
 *
 * @param start 包含起始字节偏移
 * @param end 排除结束字节偏移
 */
@DomainModel
public record ByteRange(@CoreField long start, @CoreField long end) {

  /**
   * 紧凑构造器，验证字节范围不变量。
   *
   * @throws IllegalArgumentException 当偏移为负数或 end 小于 start 时
   */
  public ByteRange {
    if (start < 0) {
      throw new IllegalArgumentException("byte_range.start must be non-negative; got " + start);
    }
    if (end < 0) {
      throw new IllegalArgumentException("byte_range.end must be non-negative; got " + end);
    }
    if (end < start) {
      throw new IllegalArgumentException(
          "byte_range.end must be >= start; start=" + start + ", end=" + end);
    }
  }

  /**
   * 创建零长度的空字节范围。
   *
   * @return start 和 end 均为 0 的空范围
   */
  public static ByteRange empty() {
    return new ByteRange(0, 0);
  }
}
