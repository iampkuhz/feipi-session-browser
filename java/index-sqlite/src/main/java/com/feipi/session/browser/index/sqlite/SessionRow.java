package com.feipi.session.browser.index.sqlite;

import java.util.Objects;

/**
 * sessions 表的类型化行数据。
 *
 * <p>承载 {@code sessions} 表全部列的不可变值对象，由 {@link ArtifactRowMapper} 从归一化制品映射而来。 所有字符串字段不允许为
 * null；空字符串表示值缺失或未知。数值字段均为非负。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 不得为空字符串，对应表 {@code PRIMARY KEY} 约束。
 *   <li>{@code agent} 不得为空字符串，对应表 {@code CHECK(agent <> '')} 约束。
 *   <li>{@code sessionId} 不得为空字符串，对应表 {@code CHECK(session_id <> '')} 约束。
 *   <li>{@code endedAt} 不得为空字符串，对应表 {@code CHECK(ended_at <> '')} 约束。
 *   <li>token、计数和时长字段均非负。
 * </ul>
 *
 * @param sessionKey 会话主键，格式 {@code agent:session_id}
 * @param agent 源适配器标识，如 {@code claude_code}、{@code codex}、{@code qoder}
 * @param sessionId provider 侧会话标识符
 * @param title 会话标题，缺失时为空字符串
 * @param projectKey 项目键，用于过滤和分组
 * @param projectName 项目显示名称
 * @param cwd 会话工作目录
 * @param startedAt 首事件 ISO8601 时间戳，缺失时为空字符串
 * @param endedAt 末事件 ISO8601 时间戳，不得为空
 * @param durationSeconds 首末事件之间的墙钟时长（秒），非负
 * @param modelExecutionSeconds 累计模型推理时长（秒），非负
 * @param toolExecutionSeconds 累计工具执行时长（秒），非负
 * @param model 模型名称，缺失时为空字符串
 * @param gitBranch Git 分支名，缺失时为空字符串
 * @param source 运行时来源标识（cli/vscode/fixture 等），缺失时为空字符串
 * @param userMessageCount 用户消息数，非负
 * @param assistantMessageCount 助手消息数，非负
 * @param toolCallCount 工具调用边声明数，非负
 * @param outputTokens 输出 token 总量，非负
 * @param freshInputTokens 非缓存输入 token 总量，非负
 * @param cacheReadTokens 缓存读取 token 总量，非负
 * @param cacheWriteTokens 缓存写入 token 总量，非负
 * @param totalTokens token 总量，非负
 * @param failedToolCount 失败工具执行数，非负
 * @param subagentInstanceCount 子 agent 实例数，非负
 * @param indexedAt 索引写入时间戳（epoch 秒），非负
 * @param fileMtime 源文件修改时间（epoch 秒），非负
 * @param filePath 源文件路径，缺失时为空字符串
 */
public record SessionRow(
    String sessionKey,
    String agent,
    String sessionId,
    String title,
    String projectKey,
    String projectName,
    String cwd,
    String startedAt,
    String endedAt,
    double durationSeconds,
    double modelExecutionSeconds,
    double toolExecutionSeconds,
    String model,
    String gitBranch,
    String source,
    long userMessageCount,
    long assistantMessageCount,
    long toolCallCount,
    long outputTokens,
    long freshInputTokens,
    long cacheReadTokens,
    long cacheWriteTokens,
    long totalTokens,
    long failedToolCount,
    long subagentInstanceCount,
    double indexedAt,
    double fileMtime,
    String filePath) {

  /**
   * 紧凑构造器，验证 sessions 表行不变量。
   *
   * <p>主键和 CHECK 约束字段不允许为空字符串；数值字段不允许为负数。 字符串字段 null 统一替换为空字符串。
   *
   * @throws IllegalArgumentException 当主键或 CHECK 约束字段为空字符串时
   * @throws IllegalArgumentException 当数值字段为负数时
   */
  public SessionRow {
    // 字符串 null → 空字符串
    title = defaultEmpty(title);
    projectKey = defaultEmpty(projectKey);
    projectName = defaultEmpty(projectName);
    cwd = defaultEmpty(cwd);
    startedAt = defaultEmpty(startedAt);
    model = defaultEmpty(model);
    gitBranch = defaultEmpty(gitBranch);
    source = defaultEmpty(source);
    filePath = defaultEmpty(filePath);

    // 主键和 CHECK 约束字段非空
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    if (sessionKey.isEmpty()) {
      throw new IllegalArgumentException("sessionKey 不得为空字符串");
    }
    Objects.requireNonNull(agent, "agent 不得为 null");
    if (agent.isEmpty()) {
      throw new IllegalArgumentException("agent 不得为空字符串");
    }
    Objects.requireNonNull(sessionId, "sessionId 不得为 null");
    if (sessionId.isEmpty()) {
      throw new IllegalArgumentException("sessionId 不得为空字符串");
    }
    Objects.requireNonNull(endedAt, "endedAt 不得为 null");
    if (endedAt.isEmpty()) {
      throw new IllegalArgumentException("endedAt 不得为空字符串");
    }

    // 数值非负
    requireNonNegative(durationSeconds, "durationSeconds");
    requireNonNegative(modelExecutionSeconds, "modelExecutionSeconds");
    requireNonNegative(toolExecutionSeconds, "toolExecutionSeconds");
    requireNonNegative(userMessageCount, "userMessageCount");
    requireNonNegative(assistantMessageCount, "assistantMessageCount");
    requireNonNegative(toolCallCount, "toolCallCount");
    requireNonNegative(outputTokens, "outputTokens");
    requireNonNegative(freshInputTokens, "freshInputTokens");
    requireNonNegative(cacheReadTokens, "cacheReadTokens");
    requireNonNegative(cacheWriteTokens, "cacheWriteTokens");
    requireNonNegative(totalTokens, "totalTokens");
    requireNonNegative(failedToolCount, "failedToolCount");
    requireNonNegative(subagentInstanceCount, "subagentInstanceCount");
    requireNonNegative(indexedAt, "indexedAt");
    requireNonNegative(fileMtime, "fileMtime");
  }

  private static String defaultEmpty(String value) {
    return value == null ? "" : value;
  }

  private static void requireNonNegative(double value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }

  private static void requireNonNegative(long value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }
}
