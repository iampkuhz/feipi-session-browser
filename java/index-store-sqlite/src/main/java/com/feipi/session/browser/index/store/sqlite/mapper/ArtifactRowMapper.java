package com.feipi.session.browser.index.store.sqlite.mapper;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 归一化制品到 index row 的唯一映射器。
 *
 * <p>把 verified {@link NormalizedSessionArtifact} 转为 {@link SessionRow} 和 {@link
 * SessionArtifactRow}。 full scan 和 incremental scan 共享同一个映射逻辑，不重复字段列表。
 *
 * <p>映射职责：
 *
 * <ul>
 *   <li>从制品 {@code session} map 提取标量字段（session_key、session_id、title 等）。
 *   <li>从 {@code calls} 列表聚合 token 用量、消息计数和工具调用声明数。
 *   <li>从 {@code toolExecutions} 列表聚合工具执行时长和失败计数。
 *   <li>将 agent enum 转为数据库字符串值。
 * </ul>
 *
 * <p>校验放置：本类信任归一化制品已通过 domain 不变量验证（schema 版本、agent 合法性、callId 唯一性等）， 只在映射边界执行 DB 约束所需的非空和非负校验，由
 * {@link SessionRow} 紧凑构造器承担。
 */
public final class ArtifactRowMapper {

  /** 制品类型标识，用于 session_artifacts 行。 */
  public static final String ARTIFACT_TYPE_NORMALIZED = "normalized";

  /** 早期 Python/main 分支写入的归一化制品类型标识。 */
  public static final String ARTIFACT_TYPE_NORMALIZED_SESSION_JSON = "normalized_session_json";

  /** 防止实例化。 */
  private ArtifactRowMapper() {}

  /**
   * 将归一化制品映射为 sessions 表行。
   *
   * <p>从 {@code artifact.session()} map 提取会话标量字段，从 {@code calls()} 和 {@code toolExecutions()}
   * 聚合统计量。缺失字段使用空字符串或零值。
   *
   * @param artifact 已通过 domain 不变量验证的归一化制品
   * @param fileMtime 源文件修改时间（epoch 秒）
   * @param filePath 源文件路径
   * @return 完整的 sessions 表行
   * @throws NullPointerException 当 artifact 为 null 时
   */
  public static SessionRow toSessionRow(
      NormalizedSessionArtifact artifact, double fileMtime, String filePath) {
    Objects.requireNonNull(artifact, "artifact 不得为 null");

    Map<String, Object> session = artifact.session();

    // 从 session map 提取标量字段
    String sessionKey = asString(session, "session_key");
    String sessionId = asString(session, "session_id");
    String title = asString(session, "title");
    String projectKey = asString(session, "project_key");
    String projectName = asString(session, "project_name");
    String cwd = asString(session, "cwd");
    String startedAt = asString(session, "started_at");
    String endedAt = asString(session, "ended_at");
    String model = asString(session, "model");
    String gitBranch = asString(session, "git_branch");
    String source = asString(session, "source");
    double durationSeconds = optionalDouble(session, "duration_seconds");

    // agent 使用 enum 的协议值
    String agent = artifact.agent().getValue();

    // 如果 session map 未提供 model，从第一个 call 取
    if (model.isEmpty() && !artifact.calls().isEmpty()) {
      model = artifact.calls().get(0).model();
    }

    // 如果 session map 未提供 ended_at，从最后一个 call 的 timestamp 取
    if (endedAt.isEmpty() && !artifact.calls().isEmpty()) {
      NormalizedCall lastCall = artifact.calls().get(artifact.calls().size() - 1);
      endedAt = lastCall.timestamp().orElse("");
    }

    // 聚合 calls 统计量；优先从 session map 读取归一化引擎统计值
    long outputTokens = 0;
    long freshInputTokens = 0;
    long cacheReadTokens = 0;
    long cacheWriteTokens = 0;
    long totalTokens = 0;
    long assistantMessageCount = 0;
    long toolCallCount = 0;
    long userMessageCount = 0;

    // 优先从 session map 读取归一化引擎统计的 assistantMessageCount
    Object sessionAssistantCount = session.get("assistantMessageCount");
    if (sessionAssistantCount instanceof Number num) {
      assistantMessageCount = num.longValue();
    } else {
      assistantMessageCount = artifact.calls().size();
    }

    // 优先从 session map 读取归一化引擎统计的 toolCallCount
    Object sessionToolCallCount = session.get("toolCallCount");
    if (sessionToolCallCount instanceof Number num) {
      toolCallCount = num.longValue();
    }

    // 优先从 session map 读取归一化引擎统计的 userMessageCount
    Object sessionUserMsgCount = session.get("userMessageCount");
    if (sessionUserMsgCount instanceof Number num) {
      userMessageCount = num.longValue();
    }

    // 优先从 session map 读取 token 字段
    Object sessionTotalTokens = session.get("totalTokens");
    if (sessionTotalTokens instanceof Number num) {
      totalTokens = num.longValue();
    }
    Object sessionOutputTokens = session.get("outputTokens");
    if (sessionOutputTokens instanceof Number num) {
      outputTokens = num.longValue();
    }
    Object sessionFreshInputTokens = session.get("freshInputTokens");
    if (sessionFreshInputTokens instanceof Number num) {
      freshInputTokens = num.longValue();
    }
    Object sessionCacheReadTokens = session.get("cacheReadTokens");
    if (sessionCacheReadTokens instanceof Number num) {
      cacheReadTokens = num.longValue();
    }
    Object sessionCacheWriteTokens = session.get("cacheWriteTokens");
    if (sessionCacheWriteTokens instanceof Number num) {
      cacheWriteTokens = num.longValue();
    }

    Set<String> subagentIds = new HashSet<>();

    for (NormalizedCall call : artifact.calls()) {
      if (sessionOutputTokens == null) {
        outputTokens += call.usage().output();
      }
      if (sessionFreshInputTokens == null) {
        freshInputTokens += call.usage().fresh();
      }
      if (sessionCacheReadTokens == null) {
        cacheReadTokens += call.usage().cacheRead();
      }
      if (sessionCacheWriteTokens == null) {
        cacheWriteTokens += call.usage().cacheWrite();
      }
      // 仅当 session map 未提供 totalTokens 时从 calls 聚合
      if (sessionTotalTokens == null) {
        totalTokens += call.usage().total();
      }
      // 仅当 session map 未提供 toolCallCount 时从 calls 聚合
      if (sessionToolCallCount == null) {
        toolCallCount += call.response().toolCallIds().size();
      }

      // 仅在 session map 未提供 userMessageCount 时回退到 scope 计数
      if (sessionUserMsgCount == null && call.scope() == CallScope.MAIN) {
        userMessageCount++;
      }
      // 统计子 agent 实例
      if (call.scope() == CallScope.SUBAGENT) {
        call.parentCallId().ifPresent(subagentIds::add);
      }
    }

    // 聚合 toolExecutions 统计量；优先从 session map 读取 failedToolCount
    long toolDurationMs = 0;
    long failedToolCount = 0;
    Object sessionFailedTools = session.get("failedToolCount");
    if (sessionFailedTools instanceof Number num) {
      failedToolCount = num.longValue();
    }

    for (NormalizedToolExecution exec : artifact.toolExecutions()) {
      toolDurationMs += exec.durationMs();
      // 仅在 session map 未提供 failedToolCount 时回退到 status 检测
      if (sessionFailedTools == null && exec.status().isPresent()) {
        failedToolCount++;
      }
    }

    // toolExecutionSeconds 从毫秒转换为秒；session map 有值时优先使用
    double toolExecSeconds = toolDurationMs / 1000.0;
    Object sessionToolExec = session.get("toolExecutionSeconds");
    if (toolExecSeconds == 0 && sessionToolExec instanceof Number num) {
      toolExecSeconds = num.doubleValue();
    }

    // modelExecutionSeconds 从 session map 读取（归一化引擎计算）
    double modelExecSeconds = 0;
    Object sessionModelExec = session.get("modelExecutionSeconds");
    if (sessionModelExec instanceof Number num) {
      modelExecSeconds = num.doubleValue();
    }

    long subagentInstanceCount = subagentIds.size();
    Object sessionSubagentInstances = session.get("subagentInstanceCount");
    if (sessionSubagentInstances instanceof Number num) {
      subagentInstanceCount = num.longValue();
    }

    // indexed_at 使用当前时间
    double indexedAt = System.currentTimeMillis() / 1000.0;

    return new SessionRow(
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
        modelExecSeconds,
        toolExecSeconds,
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
  }

  /**
   * 构建归一化制品的 session_artifacts 表行。
   *
   * @param sessionKey 会话主键
   * @param artifactPath 制品存储路径
   * @param schemaVersion 制品 schema 版本
   * @param sourcePath 源文件路径
   * @param sourceMtime 源文件修改时间（epoch 秒）
   * @param sizeBytes 制品文件大小（字节）
   * @param now 当前时间戳（epoch 秒）
   * @return session_artifacts 表行
   */
  public static SessionArtifactRow toArtifactRow(
      String sessionKey,
      String artifactPath,
      String schemaVersion,
      String sourcePath,
      double sourceMtime,
      long sizeBytes,
      double now) {
    return new SessionArtifactRow(
        sessionKey,
        ARTIFACT_TYPE_NORMALIZED,
        artifactPath,
        schemaVersion,
        sourcePath,
        sourceMtime,
        sizeBytes,
        now,
        now);
  }

  /** 从 session map 取字符串字段，null 转为空字符串。 */
  private static String asString(Map<String, Object> session, String key) {
    Object value = session.get(key);
    if (value == null) {
      return "";
    }
    return String.valueOf(value);
  }

  /** 从 session map 取可选 double 字段。 */
  private static double optionalDouble(Map<String, Object> session, String key) {
    Object value = session.get(key);
    if (value == null) {
      return 0.0;
    }
    if (value instanceof Number num) {
      return num.doubleValue();
    }
    try {
      return Double.parseDouble(String.valueOf(value));
    } catch (NumberFormatException e) {
      return 0.0;
    }
  }
}
