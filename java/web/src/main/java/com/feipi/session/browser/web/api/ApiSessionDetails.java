package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.query.api.PayloadVisibility;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.sql.SQLException;
import java.util.Optional;

/** Session Detail API/export 共享的加载与错误响应逻辑。 */
final class ApiSessionDetails {

  private ApiSessionDetails() {}

  /** 加载带 anomaly 注解的 session detail，并写出统一错误响应。 */
  static Optional<SessionDetailUseCase.AnnotatedDetail> loadAnnotatedDetail(
      Context ctx, QueryCompositionRoot queryRoot, String sessionKey, PayloadVisibility visibility)
      throws SQLException {
    try {
      Optional<SessionDetailUseCase.AnnotatedDetail> detail =
          queryRoot.sessionDetail().getDetailWithAnomalies(sessionKey, visibility);
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
