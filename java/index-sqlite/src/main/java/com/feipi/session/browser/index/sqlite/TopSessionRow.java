package com.feipi.session.browser.index.sqlite;

/**
 * Top-N 会话排行行。
 *
 * <p>对应 Python {@code get_slowest_sessions} 和 {@code get_failed_tool_sessions} 查询结果。
 * 统一两种会话排行查询的公共字段结构。
 *
 * @param sessionKey 会话主键
 * @param title 会话标题
 * @param agent agent 标识
 * @param model 模型名称
 * @param projectName 项目名称
 * @param durationSeconds 时长（秒）
 * @param failedToolCount 失败工具调用数
 * @param toolCallCount 工具调用总数
 */
public record TopSessionRow(
    String sessionKey,
    String title,
    String agent,
    String model,
    String projectName,
    double durationSeconds,
    long failedToolCount,
    long toolCallCount) {}
