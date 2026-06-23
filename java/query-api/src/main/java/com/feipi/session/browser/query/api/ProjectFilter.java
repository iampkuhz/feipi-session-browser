package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 项目过滤器。
 *
 * <p>按项目键过滤会话。空字符串表示不过滤（匹配所有项目）。 非空值直接对应 {@code sessions.project_key} 列。
 *
 * <p>校验在 factory 完成，repository 信任已验证的值。
 */
public final class ProjectFilter {

  /** 不过滤任何项目的实例。 */
  public static final ProjectFilter NONE = new ProjectFilter("");

  private final String projectKey;

  private ProjectFilter(String projectKey) {
    this.projectKey = projectKey;
  }

  /**
   * 创建项目过滤器。
   *
   * @param projectKey 项目键，空字符串表示不过滤
   * @return 新的项目过滤器
   * @throws NullPointerException 当 projectKey 为 null 时
   * @throws IllegalArgumentException 当 projectKey 包含前导或尾随空白时
   */
  public static ProjectFilter of(String projectKey) {
    Objects.requireNonNull(projectKey, "projectKey 不得为 null");
    if (!projectKey.isEmpty() && !projectKey.trim().equals(projectKey)) {
      throw new IllegalArgumentException("projectKey 不得包含前导或尾随空白: '" + projectKey + "'");
    }
    return new ProjectFilter(projectKey);
  }

  /**
   * 是否为空过滤。
   *
   * @return 当 projectKey 为空字符串时返回 true
   */
  public boolean isUnfiltered() {
    return projectKey.isEmpty();
  }

  /**
   * 获取项目键。
   *
   * @return 项目键，空字符串表示不过滤
   */
  public String projectKey() {
    return projectKey;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) return true;
    if (!(obj instanceof ProjectFilter other)) return false;
    return projectKey.equals(other.projectKey);
  }

  @Override
  public int hashCode() {
    return projectKey.hashCode();
  }

  @Override
  public String toString() {
    return isUnfiltered() ? "ProjectFilter[*]" : "ProjectFilter[" + projectKey + "]";
  }
}
