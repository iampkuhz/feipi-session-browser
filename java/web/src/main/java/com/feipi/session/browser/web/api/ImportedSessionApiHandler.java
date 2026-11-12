package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionDetailFilterEcho;
import io.javalin.http.Context;
import io.javalin.http.HttpResponseException;
import io.javalin.http.HttpStatus;
import io.javalin.http.UploadedFile;
import jakarta.servlet.ServletException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.URI;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/** 单文件上传及独立资源 API，不持有个人查询入口。 */
public final class ImportedSessionApiHandler {

  private static final Set<String> LOOPBACK_HOSTS = Set.of("localhost", "127.0.0.1", "[::1]");

  private final ImportedSessionUseCase imports;
  private final SessionApiService apiService;
  private final SessionApiRouter router;
  private final SessionDetailApiHandler details;

  /**
   * 创建独立数据范围的处理器和缓存。
   *
   * @param imports 单文件分析用例
   */
  public ImportedSessionApiHandler(ImportedSessionUseCase imports) {
    this.imports = Objects.requireNonNull(imports, "imports");
    this.apiService =
        new SessionApiService(
            (key, visibility) ->
                imports.getDetailContext(key.substring(key.indexOf(':') + 1), visibility));
    this.router = new SessionApiRouter(new SessionApiHandler(apiService));
    this.details = new SessionDetailApiHandler(this::loadDetail);
  }

  /** 接收单个 multipart 文件，拒绝额外字段、本地路径和跨源浏览器请求。 */
  public void handleCreate(Context ctx) {
    if (!sameOrigin(ctx, true)) {
      error(ctx, HttpStatus.FORBIDDEN, "origin_forbidden", "不允许跨源上传");
      return;
    }
    try {
      String contentType = ctx.header("Content-Type");
      if (contentType == null
          || !contentType.toLowerCase(java.util.Locale.ROOT).startsWith("multipart/form-data")) {
        error(ctx, HttpStatus.BAD_REQUEST, "invalid_upload", "请上传单个 JSONL 文件");
        return;
      }
      var parsedFiles = readFiles(ctx);
      if (parsedFiles.isEmpty()) {
        return;
      }
      List<UploadedFile> files = parsedFiles.get();
      var parts = ctx.req().getParts();
      if (files.size() != 1
          || ctx.uploadedFiles("file").size() != 1
          || parts.size() != 2
          || parts.stream()
                  .filter(
                      part ->
                          "source".equals(part.getName()) && part.getSubmittedFileName() == null)
                  .count()
              != 1
          || ctx.formParams("source").size() != 1) {
        error(ctx, HttpStatus.BAD_REQUEST, "invalid_upload", "仅允许一个 file 文件和一个 source 字段");
        return;
      }
      NormalizedAgent source;
      try {
        source = NormalizedAgent.fromValue(ctx.formParam("source"));
      } catch (IllegalArgumentException e) {
        error(ctx, HttpStatus.BAD_REQUEST, "invalid_source", "不支持的来源");
        return;
      }
      UploadedFile file = files.getFirst();
      if (file.size() > imports.limits().maxFileBytes()) {
        error(ctx, HttpStatus.CONTENT_TOO_LARGE, "file_too_large", "上传文件超过大小限制");
        return;
      }
      try (var input = file.content()) {
        ImportedSessionMetadata metadata = imports.create(input, file.filename(), source);
        ctx.status(HttpStatus.CREATED)
            .json(
                new ImportCreatedResponse(
                    metadata.importId(),
                    metadata.source().getValue(),
                    metadata.filename(),
                    "/imports/" + metadata.importId()));
      }
    } catch (SessionImportException e) {
      HttpStatus status =
          switch (e.code()) {
            case "file_too_large", "too_many_records", "record_too_large", "analysis_too_large" ->
                HttpStatus.CONTENT_TOO_LARGE;
            case "capacity_exceeded" -> HttpStatus.CONFLICT;
            case "service_closed" -> HttpStatus.SERVICE_UNAVAILABLE;
            case "cleanup_failed" -> HttpStatus.INTERNAL_SERVER_ERROR;
            default -> HttpStatus.BAD_REQUEST;
          };
      error(ctx, status, e.code(), e.getMessage());
    } catch (HttpResponseException e) {
      boolean tooLarge = e.getStatus() == 413;
      error(
          ctx,
          tooLarge ? HttpStatus.CONTENT_TOO_LARGE : HttpStatus.BAD_REQUEST,
          tooLarge ? "file_too_large" : "invalid_upload",
          "上传内容无效或超过限制");
    } catch (ServletException e) {
      error(ctx, HttpStatus.BAD_REQUEST, "invalid_upload", "上传内容无效");
    } catch (IOException e) {
      error(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "import_failed", "无法分析上传文件");
    }
  }

  /** Servlet 在 multipart 超限时抛 IllegalStateException；不回传解析器的内部路径或正文。 */
  private static Optional<List<UploadedFile>> readFiles(Context ctx) {
    try {
      return Optional.of(ctx.uploadedFiles());
    } catch (Exception e) {
      boolean tooLarge = isSizeLimitFailure(e);
      error(
          ctx,
          tooLarge ? HttpStatus.CONTENT_TOO_LARGE : HttpStatus.BAD_REQUEST,
          tooLarge ? "file_too_large" : "invalid_upload",
          "上传内容无效或超过限制");
      return Optional.empty();
    }
  }

  /** Jetty 会把 multipart 限额异常包装在 Servlet/异步读取异常中。 */
  private static boolean isSizeLimitFailure(Throwable failure) {
    for (Throwable cause = failure; cause != null; cause = cause.getCause()) {
      if (cause instanceof IllegalStateException
          || cause instanceof HttpResponseException response && response.getStatus() == 413) {
        return true;
      }
    }
    return false;
  }

  /** 分发同一导入范围的摘要和懒加载资源。 */
  public void handleResource(Context ctx) {
    String id = ctx.pathParam("importId");
    var metadata = imports.find(id);
    if (metadata.isEmpty()) {
      error(ctx, HttpStatus.NOT_FOUND, "not_found", "导入不存在或已失效");
      return;
    }
    String suffix = ctx.path().substring(("/api/imports/" + id + "/").length());
    switch (suffix) {
      case "meta" -> details.handleMeta(ctx);
      case "metrics" -> details.handleMetrics(ctx);
      case "diagnostics" -> details.handleDiagnostics(ctx);
      case "rounds" -> details.handleRounds(ctx);
      case "payloads" -> details.handlePayloads(ctx);
      default -> router.routeResource(ctx, metadata.get().source().getValue(), id, suffix);
    }
  }

  /** 删除独立分析后同时清空其懒加载缓存，不能继续返回已释放内容。 */
  public void handleDelete(Context ctx) {
    if (!sameOrigin(ctx, false)) {
      error(ctx, HttpStatus.FORBIDDEN, "origin_forbidden", "不允许跨源删除");
      return;
    }
    try {
      if (!imports.delete(ctx.pathParam("importId"))) {
        error(ctx, HttpStatus.NOT_FOUND, "not_found", "导入不存在或已失效");
        return;
      }
      apiService.invalidateCache();
      ctx.status(HttpStatus.NO_CONTENT);
    } catch (IOException e) {
      error(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "delete_failed", "无法删除导入分析");
    }
  }

  private SessionDetailApiHandler.LoadedDetail loadDetail(Context ctx) {
    String id = ctx.pathParam("importId");
    var metadata = imports.find(id);
    var visibility = ApiQueryParams.payloadVisibility(ctx);
    var detail = imports.getDetailContextWithAnomalies(id, visibility);
    if (metadata.isEmpty() || detail.isEmpty()) {
      error(ctx, HttpStatus.NOT_FOUND, "not_found", "导入不存在或已失效");
      return null;
    }
    return new SessionDetailApiHandler.LoadedDetail(
        new SessionDetailFilterEcho(
            metadata.get().source().getValue(), id, visibility.getValue(), "", ""),
        detail.get(),
        "/api/imports/" + id,
        false);
  }

  /** 不信任代理转发头。只对本机上传兼容浏览器遗漏的 Origin 端口。 */
  private static boolean sameOrigin(Context ctx, boolean upload) {
    String origin = ctx.header("Origin");
    if (origin == null) {
      return true;
    }
    try {
      URI supplied = URI.create(origin);
      URI current = URI.create(ctx.url());
      if (supplied.getRawUserInfo() != null
          || supplied.getRawQuery() != null
          || supplied.getRawFragment() != null
          || !"".equals(supplied.getRawPath())
          || !sameHostAndScheme(current, supplied)) {
        return false;
      }
      return effectivePort(current) == effectivePort(supplied)
          || upload && corroboratedLoopbackUpload(ctx, supplied, current);
    } catch (IllegalArgumentException e) {
      return false;
    }
  }

  private static boolean corroboratedLoopbackUpload(Context ctx, URI origin, URI current) {
    // 显式端口（包括默认端口）冲突不是“缺端口”。要求两份独立的浏览器同源证据。
    String referer = ctx.header("Referer");
    if (!origin.getHost().equalsIgnoreCase(origin.getRawAuthority())
        || !LOOPBACK_HOSTS.contains(current.getHost().toLowerCase(java.util.Locale.ROOT))
        || !"same-origin".equals(ctx.header("Sec-Fetch-Site"))
        || referer == null
        || !InetAddress.ofLiteral(ctx.req().getRemoteAddr()).isLoopbackAddress()) {
      return false;
    }
    URI page = URI.create(referer);
    return page.getRawUserInfo() == null
        && page.getRawFragment() == null
        && sameHostAndScheme(current, page)
        && effectivePort(current) == effectivePort(page);
  }

  private static boolean sameHostAndScheme(URI current, URI other) {
    return current.getScheme().equalsIgnoreCase(other.getScheme())
        && current.getHost() != null
        && current.getHost().equalsIgnoreCase(other.getHost());
  }

  private static int effectivePort(URI uri) {
    return uri.getPort() >= 0
        ? uri.getPort()
        : "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
  }

  private static void error(Context ctx, HttpStatus status, String code, String message) {
    ApiSessionDetails.sendError(ctx, status, code, message);
  }

  /**
   * 上传成功的安全导航信息。
   *
   * @param importId 独立导入标识
   * @param source 显式选择的来源
   * @param filename 显示文件名
   * @param detailUrl 独立详情 URL
   */
  public record ImportCreatedResponse(
      @JsonProperty("import_id") String importId,
      String source,
      String filename,
      @JsonProperty("detail_url") String detailUrl) {}
}
