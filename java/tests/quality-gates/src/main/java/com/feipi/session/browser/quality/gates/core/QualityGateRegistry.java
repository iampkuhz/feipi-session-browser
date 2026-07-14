package com.feipi.session.browser.quality.gates.core;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 质量门注册表。
 *
 * <p>管理已注册的 {@link QualityRule} 实例，并保持声明顺序。
 */
public final class QualityGateRegistry {

  private final Map<String, QualityRule> rules;

  private QualityGateRegistry(Map<String, QualityRule> rules) {
    this.rules = Collections.unmodifiableMap(new LinkedHashMap<>(rules));
  }

  /**
   * 按 id 顺序选择已注册的质量规则。
   *
   * @param ids 规则 id 列表。
   * @return 按请求顺序排列的规则。
   */
  public List<QualityRule> select(List<String> ids) {
    return ids.stream().map(rules::get).toList();
  }

  /**
   * 返回所有已注册的门禁 id。
   *
   * @return 不可变 id 集合。
   */
  public java.util.Set<String> registeredIds() {
    return rules.keySet();
  }

  /**
   * 创建新的 builder。
   *
   * @return builder 实例。
   */
  public static Builder builder() {
    return new Builder();
  }

  /** 注册表构建器。 */
  public static final class Builder {

    private final Map<String, QualityRule> rules = new LinkedHashMap<>();

    private Builder() {}

    /**
     * 注册一个质量门。
     *
     * @param rule 质量规则实例。
     * @return this。
     */
    public Builder register(QualityRule rule) {
      rules.put(rule.id(), rule);
      return this;
    }

    /**
     * 构建注册表。
     *
     * @return 不可变注册表。
     */
    public QualityGateRegistry build() {
      return new QualityGateRegistry(rules);
    }
  }
}
