package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.IOException;
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

  private final SessionDetailUseCase detailUseCase;
  private final ConcurrentHashMap<String, SessionApiContext> contextCache =
      new ConcurrentHashMap<>();

  /** 缓存最大条目数。 */
  private static final int MAX_CACHE_SIZE = 16;

  /**
   * 创建会话 API 服务。
   *
   * @param detailUseCase 会话详情 use case
   */
  public SessionApiService(SessionDetailUseCase detailUseCase) {
    this.detailUseCase = Objects.requireNonNull(detailUseCase, "detailUseCase 不得为 null");
  }

  /**
   * 获取指定会话的 API 上下文。
   *
   * <p>优先从缓存读取，缓存未命中时加载会话行和归一化制品，构建上下文并缓存。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return API 上下文，会话不存在时返回 empty
   * @throws SessionDataException 制品加载失败
   */
  public Optional<SessionApiContext> getContext(String sessionKey, PayloadVisibility visibility) {
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
  private Optional<SessionApiContext> loadContext(String sessionKey, PayloadVisibility visibility) {
    SessionDetailUseCase.DetailContext context;
    try {
      Optional<SessionDetailUseCase.DetailContext> loaded =
          detailUseCase.getDetailContext(sessionKey, visibility);
      if (loaded.isEmpty()) {
        return Optional.empty();
      }
      context = loaded.get();
    } catch (IOException e) {
      throw new SessionDataException("归一化制品加载失败: " + sessionKey, e);
    }

    NormalizedSessionArtifact artifact = context.artifact();
    PayloadLookup payloadLookup =
        artifact == null ? emptyPayloadLookup(visibility) : PayloadLookup.fromArtifact(artifact, visibility);
    return Optional.of(new SessionApiContext(context.detail(), artifact, payloadLookup));
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
    public SessionRecord sessionRow() {
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
