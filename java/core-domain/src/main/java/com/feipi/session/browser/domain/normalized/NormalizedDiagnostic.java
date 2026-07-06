package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.AbstractMap;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 结构化诊断信息。
 *
 * <p>诊断信息来源于 source adapter 和 normalization engine。类型保持只读 Map 兼容性，避免旧查询与测试路径为读取单个字段而重新适配。
 */
@DomainModel
public final class NormalizedDiagnostic extends AbstractMap<String, Object> {

  private final Map<String, Object> values;

  /**
   * 从 map 构造不可变诊断。
   *
   * @param values 诊断字段
   */
  public NormalizedDiagnostic(Map<String, Object> values) {
    Objects.requireNonNull(values, "values 不得为 null");
    if (values.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "diagnostic map size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    this.values = Collections.unmodifiableMap(Map.copyOf(values));
  }

  /**
   * 从 map 创建诊断。
   *
   * @param values 诊断字段
   * @return 不可变诊断
   */
  public static NormalizedDiagnostic fromMap(Map<String, Object> values) {
    return new NormalizedDiagnostic(values);
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
