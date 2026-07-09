package com.feipi.session.browser.web.model;

import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.query.api.PayloadVisibility;
import io.javalin.http.Context;
import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.Optional;

/** Session Detail 页面与导出端点共享的请求解析结果。 */
public final class SessionDetailRequest {

  private final String decodedAgent;
  private final String decodedSessionId;
  private final String sessionKey;
  private final PayloadVisibility visibility;

  private SessionDetailRequest(
      String decodedAgent,
      String decodedSessionId,
      String sessionKey,
      PayloadVisibility visibility) {
    this.decodedAgent = decodedAgent;
    this.decodedSessionId = decodedSessionId;
    this.sessionKey = sessionKey;
    this.visibility = visibility;
  }

  /** 从 Javalin context 与路径参数构建请求对象。 */
  public static SessionDetailRequest from(Context ctx, String agent, String sessionId) {
    Objects.requireNonNull(ctx, "ctx 不得为 null");
    String decodedAgent = URLDecoder.decode(agent, StandardCharsets.UTF_8);
    String decodedSessionId = URLDecoder.decode(sessionId, StandardCharsets.UTF_8);
    return new SessionDetailRequest(
        decodedAgent,
        decodedSessionId,
        decodedAgent + ":" + decodedSessionId,
        PayloadVisibilityQuery.parse(ctx));
  }

  /** 加载带 anomaly 注解的 session detail。 */
  public Optional<SessionDetailUseCase.AnnotatedDetail> load(SessionDetailUseCase useCase)
      throws IOException {
    Objects.requireNonNull(useCase, "useCase 不得为 null");
    return useCase.getDetailWithAnomalies(sessionKey, visibility);
  }

  /** 返回 URL 解码后的 agent。 */
  public String decodedAgent() {
    return decodedAgent;
  }

  /** 返回 URL 解码后的 session id。 */
  public String decodedSessionId() {
    return decodedSessionId;
  }

  /** 返回用于查询的 session key。 */
  public String sessionKey() {
    return sessionKey;
  }

  /** 返回 payload 可见性策略。 */
  public PayloadVisibility visibility() {
    return visibility;
  }
}
