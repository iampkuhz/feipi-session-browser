package com.feipi.session.browser.domain.normalized;

import java.util.List;

/**
 * 命名来源序列的有界片段；offset 是该序列跨所有内容单元的全局起始位置。
 *
 * @param name 所属逻辑来源序列的名称，同名片段连续拼接
 * @param offset 当前片段首键在完整命名序列中的零起始位置
 * @param keys 按来源顺序排列的有界键列表，不因切分重置标识
 */
public record NormalizedSequenceChunk(String name, long offset, List<String> keys) {
  /** 验证序列名、非负偏移及原有键数量上限，并保存键列表的不可变副本。 */
  public NormalizedSequenceChunk {
    if (name == null || name.isBlank() || offset < 0) {
      throw new IllegalArgumentException("sequence requires a name and nonnegative offset");
    }
    keys = List.copyOf(keys);
    if (keys.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException("sequence keys size exceeds limit");
    }
  }
}
