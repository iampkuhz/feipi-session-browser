package com.feipi.session.browser.index.sqlite;

/**
 * Top-N 项目聚合行。
 *
 * <p>对应 Python {@code get_top_projects_by_tokens} 和 {@code get_top_projects_by_tools} 查询结果。
 * 统一两种项目排行查询的公共字段结构。
 *
 * @param projectKey 项目键
 * @param projectName 项目显示名称
 * @param totalTokens token 总量
 * @param totalTools 工具调用总数
 * @param failedTools 失败工具调用总数
 * @param sessionCount 会话数
 */
public record TopProjectRow(
    String projectKey,
    String projectName,
    long totalTokens,
    long totalTools,
    long failedTools,
    long sessionCount) {}
