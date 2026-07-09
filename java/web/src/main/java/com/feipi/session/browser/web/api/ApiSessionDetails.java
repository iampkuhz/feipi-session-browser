package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.query.api.PayloadVisibility;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.util.Optional;

/** Session Detail API/export 共享的加载与错误响应逻辑。 */
final class ApiSessionDetails {

  private ApiSessionDetails() {}

  /** 加载带 anomaly 注解的 session detail，并写出统一错误响应。 */
  static Optional<SessionDetailUseCase.AnnotatedDetail> loadAnnotatedDetail(
      Context ctx, QueryCompositionRoot queryRoot, String sessionKey, PayloadVisibility visibility) {
    return loadAnnotatedDetailContext(ctx, queryRoot, sessionKey, visibility)
        .map(context -> new SessionDetailUseCase.AnnotatedDetail(context.detail(), context.anomalies()));
  }

  /** 加载带 anomaly 注解和归一化制品上下文的 session detail，并写出统一错误响应。 */
  static Optional<SessionDetailUseCase.AnnotatedDetailContext> loadAnnotatedDetailContext(
      Context ctx, QueryCompositionRoot queryRoot, String sessionKey, PayloadVisibility visibility) {
    try {
      Optional<SessionDetailUseCase.AnnotatedDetailContext> detail =
          queryRoot.sessionDetail().getDetailContextWithAnomalies(sessionKey, visibility);
      if (detail.isEmpty()) {
        sendError(ctx, HttpStatus.NOT_FOUND, "not_found", "session not found");
      }
      return detail;
    } catch (IOException e) {
      sendError(
          ctx,
          HttpStatus.INTERNAL_SERVER_ERROR,
          "artifact_error",
          "normalized artifact load failed");
      return Optional.empty();
    }
  }

  static void sendError(Context ctx, HttpStatus status, String error, String message) {
    ctx.status(status);
    ctx.json(new ApiResponses.ApiErrorResponse(error, message));
  }
}
