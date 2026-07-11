package com.feipi.session.browser.quality.gates.core;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * 质量门注册表。
 *
 * <p>管理已注册的 {@link QualityGate} 实例，支持按 id 查找。
 */
public final class QualityGateRegistry {

  private final Map<String, QualityGate> gates;

  private QualityGateRegistry(Map<String, QualityGate> gates) {
    this.gates = Collections.unmodifiableMap(new LinkedHashMap<>(gates));
  }

  /**
   * 按 id 查找已注册的质量门。
   *
   * @param id 门禁 id。
   * @return 门禁实例；未注册时返回空。
   */
  public Optional<QualityGate> find(String id) {
    return Optional.ofNullable(gates.get(id));
  }

  /**
   * 返回所有已注册的门禁 id。
   *
   * @return 不可变 id 集合。
   */
  public java.util.Set<String> registeredIds() {
    return gates.keySet();
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

    private final Map<String, QualityGate> gates = new LinkedHashMap<>();

    private Builder() {}

    /**
     * 注册一个质量门。
     *
     * @param gate 质量门实例。
     * @return this。
     */
    public Builder register(QualityGate gate) {
      gates.put(gate.id(), gate);
      return this;
    }

    /**
     * 构建注册表。
     *
     * @return 不可变注册表。
     */
    public QualityGateRegistry build() {
      return new QualityGateRegistry(gates);
    }
  }
}
