package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.sqlite.NormalizedArtifactLoader;
import com.feipi.session.browser.index.sqlite.PayloadLookup;
import com.feipi.session.browser.index.sqlite.SessionArtifactRow;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionDetailAssembler;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.IOException;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * JSON API 会话数据服务。
 *
 * <p>为 JSON API 端点提供会话数据加载和缓存。加载 {@link SessionDetail} 和 {@link NormalizedSessionArtifact}， 构建
 * {@link SessionApiContext} 供各端点消费。
 *
 * <p>缓存策略：使用有界内存缓存，避免同一会话的多次 API 请求重复解析大制品文件。
 *
 * <p>校验放置：sessionKey 格式由 Web boundary 在入口完成校验，本服务信任已验证的 sessionKey。
 */
public final class SessionApiService {

  private final SessionDetailRepository detailRepository;
  private final ConcurrentHashMap<String, SessionApiContext> contextCache =
      new ConcurrentHashMap<>();

  /** 缓存最大条目数。 */
  private static final int MAX_CACHE_SIZE = 16;

  /**
   * 创建会话 API 服务。
   *
   * @param detailRepository 会话详情仓库
   */
  public SessionApiService(SessionDetailRepository detailRepository) {
    this.detailRepository = Objects.requireNonNull(detailRepository, "detailRepository 不得为 null");
  }

  /**
   * 获取指定会话的 API 上下文。
   *
   * <p>优先从缓存读取，缓存未命中时加载会话行和归一化制品，构建上下文并缓存。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return API 上下文，会话不存在时返回 empty
   * @throws SQLException 数据库查询失败
   * @throws SessionDataException 制品加载失败
   */
  public Optional<SessionApiContext> getContext(String sessionKey, PayloadVisibility visibility)
      throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    String cacheKey = sessionKey + ":" + visibility.name();
    SessionApiContext cached = contextCache.get(cacheKey);
    if (cached != null) {
      return Optional.of(cached);
    }

    Optional<SessionApiContext> context = loadContext(sessionKey, visibility);
    context.ifPresent(ctx -> putCache(cacheKey, ctx));
    return context;
  }

  /** 加载会话数据并构建 API 上下文。 */
  private Optional<SessionApiContext> loadContext(String sessionKey, PayloadVisibility visibility)
      throws SQLException {
    Optional<SessionRow> rowOpt = detailRepository.findSessionRow(sessionKey);
    if (rowOpt.isEmpty()) {
      return Optional.empty();
    }

    SessionRow row = rowOpt.get();
    Optional<SessionArtifactRow> artifactRowOpt =
        detailRepository.findNormalizedArtifact(sessionKey);

    if (artifactRowOpt.isEmpty()) {
      // 无制品：返回仅行数据的上下文，使用空 payload lookup
      SessionDetail detail = SessionDetail.rowOnly(row, visibility);
      PayloadLookup emptyLookup = emptyPayloadLookup(visibility);
      return Optional.of(new SessionApiContext(detail, null, emptyLookup));
    }

    // 加载归一化制品
    Path artifactPath = Path.of(artifactRowOpt.get().path());
    NormalizedSessionArtifact artifact;
    try {
      artifact = NormalizedArtifactLoader.load(artifactPath);
    } catch (IOException e) {
      throw new SessionDataException("归一化制品加载失败: " + sessionKey, e);
    }

    SessionDetail detail = buildDetail(row, artifact, visibility, artifactRowOpt.get().path());
    PayloadLookup payloadLookup = PayloadLookup.fromArtifact(artifact, visibility);

    return Optional.of(new SessionApiContext(detail, artifact, payloadLookup));
  }

  /** 装配会话详情。 */
  private static SessionDetail buildDetail(
      SessionRow row,
      NormalizedSessionArtifact artifact,
      PayloadVisibility visibility,
      String artifactPath) {
    return SessionDetailAssembler.assemble(row, artifact, visibility, artifactPath, 0);
  }

  /** 创建空 payload lookup，用于无制品场景。 */
  private static PayloadLookup emptyPayloadLookup(PayloadVisibility visibility) {
    NormalizedSessionArtifact empty =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            Map.of(),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    return PayloadLookup.fromArtifact(empty, visibility);
  }

  /** 有界缓存写入。 */
  private void putCache(String key, SessionApiContext ctx) {
    if (contextCache.size() >= MAX_CACHE_SIZE) {
      contextCache.clear();
    }
    contextCache.put(key, ctx);
  }

  /**
   * 会话数据加载异常。
   *
   * <p>制品文件读取失败时抛出，由 Web 异常处理器转为 500 响应。
   */
  public static final class SessionDataException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    /**
     * 创建制品加载异常。
     *
     * @param message 错误描述
     * @param cause 原始异常
     */
    public SessionDataException(String message, Throwable cause) {
      super(message, cause);
    }
  }

  /**
   * 会话 API 上下文。
   *
   * <p>聚合一次会话的 API 所需全部数据：行数据、轮次、制品和 payload 查找表。
   *
   * @param detail 会话详情（包含行数据、轮次和 payload 来源）
   * @param artifact 归一化制品，无制品时为 null
   * @param payloadLookup payload 查找表
   */
  public record SessionApiContext(
      SessionDetail detail, NormalizedSessionArtifact artifact, PayloadLookup payloadLookup) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当 detail 或 payloadLookup 为 null 时
     */
    public SessionApiContext {
      Objects.requireNonNull(detail, "detail 不得为 null");
      Objects.requireNonNull(payloadLookup, "payloadLookup 不得为 null");
    }

    /** 获取会话行数据。 */
    public SessionRow sessionRow() {
      return detail.sessionRow();
    }

    /** 获取轮次列表。 */
    public List<CallRound> rounds() {
      return detail.rounds();
    }

    /** 获取归一化调用列表，无制品时返回空列表。 */
    public List<NormalizedCall> calls() {
      return artifact != null ? artifact.calls() : List.of();
    }

    /** 获取工具执行列表，无制品时返回空列表。 */
    public List<NormalizedToolExecution> toolExecutions() {
      return artifact != null ? artifact.toolExecutions() : List.of();
    }

    /** 按 callId 查找归一化调用。 */
    public Optional<NormalizedCall> findCall(String callId) {
      return calls().stream().filter(c -> c.callId().equals(callId)).findFirst();
    }

    /** 查找指定轮次（1-based index）。 */
    public Optional<CallRound> findRound(int roundIndex) {
      if (roundIndex < 1 || roundIndex > rounds().size()) {
        return Optional.empty();
      }
      return Optional.of(rounds().get(roundIndex - 1));
    }

    /** 查找轮次内的归一化调用。 */
    public List<NormalizedCall> callsInRound(CallRound round) {
      return calls().stream().filter(c -> round.calls().contains(c.callId())).toList();
    }

    /** 查找指定轮次内特定索引的调用（0-based）。 */
    public Optional<NormalizedCall> callAtRound(CallRound round, int callIndexInRound) {
      List<NormalizedCall> roundCalls = callsInRound(round);
      if (callIndexInRound < 0 || callIndexInRound >= roundCalls.size()) {
        return Optional.empty();
      }
      return Optional.of(roundCalls.get(callIndexInRound));
    }

    /** 查找特定作用域的调用。 */
    public List<NormalizedCall> findCallsByScope(CallScope scope) {
      return calls().stream().filter(c -> c.scope() == scope).toList();
    }
  }
}
