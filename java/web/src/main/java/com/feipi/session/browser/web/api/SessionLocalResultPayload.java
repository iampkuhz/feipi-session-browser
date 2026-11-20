package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import com.feipi.session.browser.web.IndexSnapshotGuard;
import com.feipi.session.browser.web.api.SessionApiService.SessionApiContext;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.util.List;

/** 现 payload opt-in 的请求内适配；无缓存、registry 或默认投影入口。 */
final class SessionLocalResultPayload {
  private SessionLocalResultPayload() {}

  static void send(Context ctx, SessionApiContext session, String payload) throws IOException {
    ctx.header("Cache-Control", "no-store");
    try {
      int limit = limit(ctx.queryParam("limit"));
      String path = ctx.path();
      int marker = path.lastIndexOf("/payload/");
      if (marker < 0) throw new IllegalArgumentException("invalid payload route");
      String base = path.substring(0, marker);
      String frozen = ctx.attribute(IndexSnapshotGuard.PAGE_GENERATION);
      if (!base.startsWith("/api/imports/") && frozen == null) {
        ApiSessionDetails.sendError(
            ctx,
            HttpStatus.INTERNAL_SERVER_ERROR,
            "snapshot_unavailable",
            "frozen snapshot unavailable; retry original payload");
        return;
      }
      if (session.content() == null) {
        notFound(ctx);
        return;
      }
      var operation =
          new Operation(
              session,
              base,
              (frozen == null ? "import" : frozen) + "|" + session.detail().cacheKey(),
              session.detail().visibility().getValue(),
              limit);
      String occurrence = ctx.queryParam("occurrence");
      String target = ctx.queryParam("target");
      if (occurrence != null && target != null
          || ctx.queryParam("cursor") != null && target != null)
        throw new IllegalArgumentException("target cannot be combined with occurrence or cursor");
      if (occurrence == null) operation.results(ctx, payload, target);
      else operation.relations(ctx, payload, occurrence);
    } catch (SessionContentCursor.StaleHandleException exception) {
      ApiSessionDetails.sendError(
          ctx,
          HttpStatus.CONFLICT,
          "index_generation_changed",
          "content changed; reopen original payload");
    } catch (IllegalArgumentException exception) {
      ApiSessionDetails.sendError(
          ctx, HttpStatus.BAD_REQUEST, "bad_request", "invalid local result query or handle");
    }
  }

  private static int limit(String value) {
    int result = value == null ? 20 : Integer.parseInt(value);
    if (result < 1 || result > 100) throw new IllegalArgumentException("limit within 1..100");
    return result;
  }

  /**
   * 单次 API 操作的冻结范围与共享读取器，不跨请求保留。
   *
   * @param session 本次操作的冻结内容上下文
   * @param base 当前 normal 或 import API 基址
   * @param generation 当前冻结发布代与内容代
   * @param visibility 当前正文可见性策略
   * @param limit 当前手动窗口大小
   */
  private record Operation(
      SessionApiContext session, String base, String generation, String visibility, int limit) {
    private String scope(String kind, String payload, String occurrence) {
      var value = new StringBuilder();
      for (String part :
          List.of(base, visibility, Integer.toString(limit), kind, payload, occurrence))
        value.append(part.length()).append(':').append(part);
      return value.toString();
    }

    private String seal(String kind, String payload, String occurrence, List<String> values) {
      return SessionContentCursor.seal(scope(kind, payload, occurrence), generation, values);
    }

    private List<String> open(
        String token, String kind, String payload, String occurrence, int size) {
      var values = SessionContentCursor.open(token, scope(kind, payload, occurrence), generation);
      if (values.size() != size) throw new IllegalArgumentException("invalid handle arity");
      return values;
    }

    private long offset(Context ctx, String payload, String occurrence) {
      String cursor = ctx.queryParam("cursor");
      if (cursor == null) return 0;
      long value = Long.parseLong(open(cursor, "cursor", payload, occurrence, 1).getFirst());
      if (value < 0) throw new IllegalArgumentException("negative offset");
      return value;
    }

    private String next(String payload, String occurrence, Long offset) {
      return offset == null
          ? null
          : seal("cursor", payload, occurrence, List.of(offset.toString()));
    }

    private String occurrence(String payload, String id) {
      return id.isEmpty() ? "" : seal("occurrence", payload, "", List.of(id));
    }

    private void results(Context ctx, String payload, String target) throws IOException {
      var expected = target == null ? null : open(target, "target", payload, "", 2);
      long start = offset(ctx, payload, "");
      SessionContentReader reader = session.contentReader();
      PayloadLookup.LocalResults page;
      try {
        page =
            reader.localResults(
                payload,
                start,
                limit,
                expected == null ? null : expected.get(1),
                session.detail().visibility());
      } catch (IllegalArgumentException exception) {
        notFound(ctx);
        return;
      }
      if (expected != null
          && page.references().stream()
              .noneMatch(
                  ref ->
                      ref.referenceId().equals(expected.get(1))
                          && ref.occurrenceId().equals(expected.getFirst()))) {
        notFound(ctx);
        return;
      }
      var items = new java.util.ArrayList<ApiResponses.LocalResultItem>();
      for (var item : page.occurrences())
        items.add(
            new ApiResponses.LocalResultItem(
                "",
                occurrence(payload, item.occurrenceId()),
                item.toolId(),
                item.toolName(),
                item.order(),
                item.identity(),
                item.content(),
                items.size() < 20
                    ? relationPage(
                        payload,
                        item.occurrenceId(),
                        reader.localResultRelations(item.occurrenceId(), 0, 1, null))
                    : null));
      for (var ref : page.references())
        items.add(
            new ApiResponses.LocalResultItem(
                ref.referenceId(),
                occurrence(payload, ref.occurrenceId()),
                ref.toolId(),
                ref.toolName(),
                ref.position(),
                ref.identity(),
                ref.content(),
                null));
      var entry = reader.payload(payload, session.detail().visibility());
      if (entry.isEmpty()) {
        notFound(ctx);
        return;
      }
      boolean available = !entry.get().content().isEmpty();
      if (entry.get().kind() == com.feipi.session.browser.query.api.PayloadSourceKind.TOOL_RESULT)
        available =
            SessionContentPreviews.read(session.content()).hasToolResult(entry.get().callId());
      ctx.json(
          new ApiResponses.LocalResultPayloadResponse(
              SessionApiHandler.payloadResponse(entry.get(), available),
              new ApiResponses.LocalResultPage(
                  List.copyOf(items),
                  page.offset(),
                  next(payload, "", page.nextCursor()),
                  page.coverage(),
                  page.reason(),
                  expected == null ? "" : expected.get(1)),
              null));
    }

    private void relations(Context ctx, String payload, String token) throws IOException {
      var identity = open(token, "occurrence", payload, "", 1);
      String id = identity.getFirst();
      long start = offset(ctx, payload, id);
      SessionContentReader reader = session.contentReader();
      PayloadLookup.LocalResultRelations page;
      try {
        // 同一 reader 重新核验入口确属当前 payload，不信任签名替代来源资格。
        boolean contains = reader.localResultBelongsToPayload(payload, id);
        if (!contains) {
          notFound(ctx);
          return;
        }
        page = reader.localResultRelations(id, start, limit, null);
      } catch (IllegalArgumentException exception) {
        notFound(ctx);
        return;
      }
      ctx.json(
          new ApiResponses.LocalResultPayloadResponse(null, null, relationPage(payload, id, page)));
    }

    private ApiResponses.LocalRelationsPage relationPage(
        String payload, String id, PayloadLookup.LocalResultRelations page) {
      var policy =
          SensitiveFieldPolicy.fromVisibility(
              com.feipi.session.browser.query.api.PayloadVisibility.fromValue(visibility));
      var targets =
          page.targets().stream()
              .map(
                  item ->
                      new ApiResponses.LocalRelationTarget(
                          policy.applyMasking(item.callId()),
                          item.requestPayloadId(),
                          item.referenceId(),
                          seal(
                              "target",
                              item.requestPayloadId(),
                              "",
                              List.of(id, item.referenceId())),
                          base + "/payload/" + ApiQueryParams.url(item.requestPayloadId()),
                          item.recordIndex(),
                          item.scope(),
                          "/attribution/call/" + ApiQueryParams.url(item.callId()) + "/request"))
              .toList();
      return new ApiResponses.LocalRelationsPage(
          targets,
          page.offset(),
          next(payload, id, page.nextCursor()),
          page.coverage(),
          page.reason(),
          page.identity());
    }
  }

  private static void notFound(Context ctx) {
    ApiSessionDetails.sendError(
        ctx,
        HttpStatus.NOT_FOUND,
        "not_found",
        "local result or exact containment target not found");
  }
}
