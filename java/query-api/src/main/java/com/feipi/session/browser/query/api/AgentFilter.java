package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * agent 过滤器。
 *
 * <p>按源适配器标识过滤会话。空字符串表示不过滤（匹配所有 agent）。 非空值必须是合法的 agent 标识（如 {@code claude_code}、{@code
 * codex}、{@code qoder}）。
 *
 * <p>校验在 factory 完成：agent 值不为 null，trim 后不得包含空白字符。 repository 信任已验证的值，直接作为参数化 SQL 绑定值。
 */
public final class AgentFilter {

  /** 不过滤任何 agent 的实例。 */
  public static final AgentFilter NONE = new AgentFilter("");

  private final String agent;

  private AgentFilter(String agent) {
    this.agent = agent;
  }

  /**
   * 创建 agent 过滤器。
   *
   * @param agent agent 标识，空字符串表示不过滤
   * @return 新的 agent 过滤器
   * @throws NullPointerException 当 agent 为 null 时
   * @throws IllegalArgumentException 当 agent 包含空白字符或为空字符串
   */
  public static AgentFilter of(String agent) {
    Objects.requireNonNull(agent, "agent 不得为 null");
    String trimmed = agent.trim();
    if (!trimmed.isEmpty() && !trimmed.equals(agent)) {
      throw new IllegalArgumentException("agent 不得包含前导或尾随空白: '" + agent + "'");
    }
    return new AgentFilter(trimmed);
  }

  /**
   * 是否为空过滤（不过滤任何 agent）。
   *
   * @return 当 agent 为空字符串时返回 true
   */
  public boolean isUnfiltered() {
    return agent.isEmpty();
  }

  /**
   * 获取 agent 值。
   *
   * @return agent 标识，空字符串表示不过滤
   */
  public String agent() {
    return agent;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof AgentFilter other)) return false;
    return agent.equals(other.agent);
  }

  @Override
  public int hashCode() {
    return agent.hashCode();
  }

  @Override
  public String toString() {
    return isUnfiltered() ? "AgentFilter[*]" : "AgentFilter[" + agent + "]";
  }
}
