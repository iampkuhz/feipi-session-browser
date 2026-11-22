package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import io.javalin.http.BadRequestResponse;
import io.javalin.http.NotFoundResponse;
import java.io.IOException;
import java.util.List;

/** 将证据定位到本次请求范围内的已记录成员，不从编号或名称推断归属。 */
final class RoundTarget {
  private RoundTarget() {}

  static int rowOffset(List<SessionDetailApiResponses.RoundIndexDto> rows, String target) {
    int round;
    try {
      round = Integer.parseInt(target);
      if (round <= 0) throw new NumberFormatException();
    } catch (NumberFormatException exception) {
      throw (BadRequestResponse)
          new BadRequestResponse("invalid round target").initCause(exception);
    }
    for (int i = 0; i < rows.size(); i++) if (rows.get(i).roundIndex() == round) return i;
    throw new NotFoundResponse("round target not found in this scope");
  }

  static long memberOffset(
      NormalizedSessionContent content,
      ContentRoundIndex index,
      int round,
      String target,
      boolean tool)
      throws IOException {
    String owner = tool ? declaringCall(content, target) : target;
    long offset = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) {
          if (index.roundIndexForCall(call.callId()).orElse(0) != round) continue;
          if (owner.equals(call.callId())) return offset;
          offset++;
        }
      }
    }
    throw new NotFoundResponse("member target not found in this round");
  }

  private static String declaringCall(NormalizedSessionContent content, String target)
      throws IOException {
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var tool : cursor.next().toolExecutions()) {
          if (target.equals(tool.toolCallId())) return tool.declaredByCallId();
        }
      }
    }
    throw new NotFoundResponse("tool target not found in this scope");
  }
}
