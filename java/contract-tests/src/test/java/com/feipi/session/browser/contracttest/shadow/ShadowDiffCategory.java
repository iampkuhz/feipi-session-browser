package com.feipi.session.browser.contracttest.shadow;

/**
 * Shadow 对比差异分类。
 *
 * <p>用于将两条归一化结果的差异分为四个级别，支持 Java-first 切流前的验收判定。
 */
public enum ShadowDiffCategory {

  /** 两条结果深度一致，所有可比较字段完全相同。 */
  EXACT_MATCH("exact_match"),

  /**
   * 存在差异但不影响下游消费。
   *
   * <p>典型场景：时间戳精度变化、Map 键序不同、空集合与 null 的差异、 诊断信息顺序变化等。这些差异不会改变用户可见的查询结果。
   */
  COMPATIBLE_DIFFERENCE("compatible_difference"),

  /**
   * 存在破坏性差异，可能导致下游行为变化。
   *
   * <p>典型场景：调用数量不同、token 总量不一致、工具执行关联断裂、 schema 版本变化。需要人工审查后决定是否阻塞切流。
   */
  BREAKING_DIFFERENCE("breaking_difference"),

  /**
   * 无法完成对比。
   *
   * <p>典型场景：一侧解析失败而另一侧成功、两侧 agent 标识不同、 结构类型不兼容。
   */
  INCOMPARABLE("incomparable");

  private final String value;

  ShadowDiffCategory(String value) {
    this.value = value;
  }

  /**
   * 返回该分类的稳定字符串值。
   *
   * @return 非 null 的分类值
   */
  public String getValue() {
    return value;
  }
}
