package com.feipi.session.browser.index.store.sqlite.mapper;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import com.feipi.session.browser.index.api.query.RoundAssembler;
import com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import java.util.List;
import java.util.Map;
import java.util.Objects;

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
    var aggregate = new ContentSessionAggregate();
    artifact.calls().forEach(aggregate::add);
    artifact.toolExecutions().forEach(aggregate::add);
    aggregate.sequenceObserved =
        artifact.sourceUnitSequences().values().stream().anyMatch(v -> !v.isEmpty());
    long users = count(artifact.session(), "userMessageCount", aggregate.mainCalls);
    return toRow(
        artifact.session(),
        artifact.agent().getValue(),
        aggregate,
        RoundAssembler.buildRounds(artifact, users).size(),
        artifact.agent() == NormalizedAgent.CODEX
            ? modelCalls(artifact.agent(), artifact.calls())
            : null,
        fileMtime,
        filePath);
  }

  /** 通过有界遍历映射完整逻辑会话，不构造伪造的旧格式制品。 */
  public static SessionRow toContentSessionRow(
      com.feipi.session.browser.domain.normalized.NormalizedSessionContent content,
      double fileMtime,
      String filePath)
      throws java.io.IOException {
    Objects.requireNonNull(content, "content");
    var aggregate = new ContentSessionAggregate();
    var agent = content.header().agent();
    boolean codex = agent == NormalizedAgent.CODEX;
    long modelCalls = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        unit.calls().forEach(aggregate::add);
        if (codex) modelCalls += modelCalls(agent, unit.calls());
        unit.toolExecutions().forEach(aggregate::add);
        aggregate.sequenceObserved |=
            unit.sourceUnitSequences().stream().anyMatch(v -> !v.keys().isEmpty());
      }
    }
    Map<String, Object> session = content.header().session();
    long users = count(session, "userMessageCount", aggregate.mainCalls);
    return toRow(
        session,
        agent.getValue(),
        aggregate,
        ContentRoundIndex.build(content, users).roundCount(),
        codex ? modelCalls : null,
        fileMtime,
        filePath);
  }

  private static long modelCalls(NormalizedAgent agent, List<NormalizedCall> calls) {
    return calls.stream()
        .filter(call -> !ContentRoundIndex.modelCallEvidence(agent, call).isEmpty())
        .count();
  }

  private static SessionRow toRow(
      Map<String, Object> session,
      String agent,
      ContentSessionAggregate aggregate,
      long rounds,
      Long modelCalls,
      double fileMtime,
      String filePath) {
    long users = count(session, "userMessageCount", aggregate.mainCalls);
    boolean measured =
        Boolean.TRUE.equals(session.get("contentMeasured"))
            || users > 0
            || aggregate.calls > 0
            || aggregate.tools > 0
            || aggregate.sequenceObserved;
    String model = asString(session, "model");
    String endedAt = asString(session, "ended_at");
    double toolSeconds = aggregate.toolDurationMs / 1000.0;
    if (toolSeconds == 0 && session.get("toolExecutionSeconds") instanceof Number value)
      toolSeconds = value.doubleValue();
    return new SessionRow(
        asString(session, "session_key"),
        agent,
        asString(session, "session_id"),
        asString(session, "title"),
        asString(session, "project_key"),
        asString(session, "project_name"),
        asString(session, "cwd"),
        asString(session, "started_at"),
        endedAt.isEmpty() ? aggregate.lastTimestamp : endedAt,
        optionalDouble(session, "duration_seconds"),
        number(session, "modelExecutionSeconds"),
        toolSeconds,
        model.isEmpty() ? aggregate.firstModel : model,
        asString(session, "git_branch"),
        asString(session, "source"),
        users,
        session.get("assistantMessageCount") instanceof Number assistants
            ? assistants.longValue()
            : aggregate.calls,
        count(session, "toolCallCount", aggregate.toolCalls),
        count(session, "outputTokens", aggregate.output),
        count(session, "freshInputTokens", aggregate.fresh),
        count(session, "cacheReadTokens", aggregate.cacheRead),
        count(session, "cacheWriteTokens", aggregate.cacheWrite),
        count(session, "totalTokens", aggregate.total),
        count(session, "failedToolCount", aggregate.failedTools),
        session.get("subagentInstanceCount") instanceof Number n
            ? n.longValue()
            : aggregate.subagentIds.size(),
        System.currentTimeMillis() / 1000.0,
        fileMtime,
        filePath,
        TokenProvenance.fromMetadata(session),
        SessionTiming.fromMetadata(session),
        measured ? rounds : null,
        measured ? aggregate.calls : null,
        measured,
        Boolean.TRUE.equals(session.get("userMessageCountMeasured")),
        Boolean.TRUE.equals(session.get("assistantMessageCountMeasured")),
        modelCalls);
  }

  private static long count(Map<String, Object> session, String key, long fallback) {
    Object value = session.get(key);
    return value == null ? fallback : value instanceof Number number ? number.longValue() : 0;
  }

  private static double number(Map<String, Object> session, String key) {
    return session.get(key) instanceof Number number ? number.doubleValue() : 0;
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
