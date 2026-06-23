package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 模型过滤器。
 *
 * <p>按模型名称过滤会话。空字符串表示不过滤（匹配所有模型）。 非空值直接对应 {@code sessions.model} 列。
 *
 * <p>校验在 factory 完成，repository 信任已验证的值。
 */
public final class ModelFilter {

  /** 不过滤任何模型的实例。 */
  public static final ModelFilter NONE = new ModelFilter("");

  private final String model;

  private ModelFilter(String model) {
    this.model = model;
  }

  /**
   * 创建模型过滤器。
   *
   * @param model 模型名称，空字符串表示不过滤
   * @return 新的模型过滤器
   * @throws NullPointerException 当 model 为 null 时
   * @throws IllegalArgumentException 当 model 包含前导或尾随空白时
   */
  public static ModelFilter of(String model) {
    Objects.requireNonNull(model, "model 不得为 null");
    if (!model.isEmpty() && !model.trim().equals(model)) {
      throw new IllegalArgumentException("model 不得包含前导或尾随空白: '" + model + "'");
    }
    return new ModelFilter(model);
  }

  /**
   * 是否为空过滤。
   *
   * @return 当 model 为空字符串时返回 true
   */
  public boolean isUnfiltered() {
    return model.isEmpty();
  }

  /**
   * 获取模型名称。
   *
   * @return 模型名称，空字符串表示不过滤
   */
  public String model() {
    return model;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof ModelFilter other)) return false;
    return model.equals(other.model);
  }

  @Override
  public int hashCode() {
    return model.hashCode();
  }

  @Override
  public String toString() {
    return isUnfiltered() ? "ModelFilter[*]" : "ModelFilter[" + model + "]";
  }
}
