package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.AbstractMap;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 结构化会话元数据。
 *
 * <p>该类型替代顶层 artifact 中的裸 {@code Map<String, Object>} 字段，同时实现只读 Map 接口， 让扫描、索引和测试路径可以继续使用既有 map
 * 访问方式。新增字段应先进入这里，再由 writer 决定外部 JSON 命名。
 */
@DomainModel
public final class NormalizedSessionMetadata extends AbstractMap<String, Object> {

  private final Map<String, Object> values;

  /**
   * 从 map 构造不可变元数据。
   *
   * @param values 会话元数据键值
   */
  public NormalizedSessionMetadata(Map<String, Object> values) {
    Objects.requireNonNull(values, "values 不得为 null");
    if (values.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "session map size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    this.values = Collections.unmodifiableMap(Map.copyOf(values));
  }

  /**
   * 从 map 创建元数据。
   *
   * @param values 会话元数据键值
   * @return 不可变元数据
   */
  public static NormalizedSessionMetadata fromMap(Map<String, Object> values) {
    return new NormalizedSessionMetadata(values);
  }

  /**
   * 返回普通 map 视图。
   *
   * @return 不可变 map
   */
  public Map<String, Object> toMap() {
    return values;
  }

  /**
   * 返回只读条目集合。
   *
   * @return 不可变条目集合
   */
  @Override
  public Set<Entry<String, Object>> entrySet() {
    return values.entrySet();
  }
}
