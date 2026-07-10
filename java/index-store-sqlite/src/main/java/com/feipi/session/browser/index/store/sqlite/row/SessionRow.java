package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.index.store.sqlite.mapper.ArtifactRowMapper;
import com.feipi.session.browser.validation.Finite;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

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
    /* 会话主键，格式 agent:session_id。 */ @NotBlank String sessionKey,
    /* 源适配器标识，如 claude_code、codex、qoder。 */ @NotBlank String agent,
    /* provider 侧会话标识符。 */ @NotBlank String sessionId,
    /* 会话标题，缺失时为空字符串。 */ String title,
    /* 项目键，用于过滤和分组。 */ String projectKey,
    /* 项目显示名称。 */ String projectName,
    /* 会话工作目录。 */ String cwd,
    /* 首事件 ISO8601 时间戳，缺失时为空字符串。 */ String startedAt,
    /* 末事件 ISO8601 时间戳，不得为空。 */ @NotBlank String endedAt,
    /* 首末事件之间的墙钟时长（秒），非负。 */ @Finite @PositiveOrZero double durationSeconds,
    /* 累计模型推理时长（秒），非负。 */ @Finite @PositiveOrZero double modelExecutionSeconds,
    /* 累计工具执行时长（秒），非负。 */ @Finite @PositiveOrZero double toolExecutionSeconds,
    /* 模型名称，缺失时为空字符串。 */ String model,
    /* Git 分支名，缺失时为空字符串。 */ String gitBranch,
    /* 运行时来源标识（cli/vscode/fixture 等），缺失时为空字符串。 */ String source,
    /* 用户消息数，非负。 */ @PositiveOrZero long userMessageCount,
    /* 助手消息数，非负。 */ @PositiveOrZero long assistantMessageCount,
    /* 工具调用边声明数，非负。 */ @PositiveOrZero long toolCallCount,
    /* 输出 token 总量，非负。 */ @PositiveOrZero long outputTokens,
    /* 非缓存输入 token 总量，非负。 */ @PositiveOrZero long freshInputTokens,
    /* 缓存读取 token 总量，非负。 */ @PositiveOrZero long cacheReadTokens,
    /* 缓存写入 token 总量，非负。 */ @PositiveOrZero long cacheWriteTokens,
    /* token 总量，非负。 */ @PositiveOrZero long totalTokens,
    /* 失败工具执行数，非负。 */ @PositiveOrZero long failedToolCount,
    /* 子 agent 实例数，非负。 */ @PositiveOrZero long subagentInstanceCount,
    /* 索引写入时间戳（epoch 秒），非负。 */ @PositiveOrZero double indexedAt,
    /* 源文件修改时间（epoch 秒），非负。 */ @PositiveOrZero double fileMtime,
    /* 源文件路径，缺失时为空字符串。 */ String filePath)
    implements SessionRecord {

  /**
   * 紧凑构造器，校验 record component 约束并应用默认值。
   *
   * <p>主键和 CHECK 约束字段由 {@link ValidationSupport} 校验非空；字符串字段 null 统一替换为空字符串。
   *
   * @throws IllegalArgumentException 当主键或 CHECK 约束字段为空字符串时
   * @throws IllegalArgumentException 当数值字段为负数时
   */
  public SessionRow {
    ValidationSupport.validateCanonicalConstructor(
        SessionRow.class,
        sessionKey,
        agent,
        sessionId,
        title,
        projectKey,
        projectName,
        cwd,
        startedAt,
        endedAt,
        durationSeconds,
        modelExecutionSeconds,
        toolExecutionSeconds,
        model,
        gitBranch,
        source,
        userMessageCount,
        assistantMessageCount,
        toolCallCount,
        outputTokens,
        freshInputTokens,
        cacheReadTokens,
        cacheWriteTokens,
        totalTokens,
        failedToolCount,
        subagentInstanceCount,
        indexedAt,
        fileMtime,
        filePath);

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
  }

  private static String defaultEmpty(String value) {
    return value == null ? "" : value;
  }
}
