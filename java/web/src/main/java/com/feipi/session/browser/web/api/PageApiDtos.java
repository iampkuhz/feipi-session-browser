package com.feipi.session.browser.web.api;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.common.validation.ParamChecks;
import com.feipi.session.browser.common.validation.TokenChecks;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

/** API-first 页面数据契约共享 DTO。 */
public final class PageApiDtos {

  private PageApiDtos() {}

  /**
   * 表示 TokenSegments 数据。
   *
   * @param fresh fresh input token 数量。
   * @param cacheRead cache read token 数量。
   * @param cacheWrite cache write token 数量。
   * @param output 该字段在 API 响应中的业务值。
   * @param total 汇总数量。
   */
  public record TokenSegments(
      long fresh, long cacheRead, long cacheWrite, long output, long total) {

    /** 校验字段和业务不变量。 */
    public TokenSegments {
      TokenChecks.requireUsageSegments(fresh, cacheRead, cacheWrite, output, total, "");
    }

    /** 根据原始 component 值构建 token 分段。 */
    public static TokenSegments of(long fresh, long cacheRead, long cacheWrite, long output) {
      return new TokenSegments(
          fresh,
          cacheRead,
          cacheWrite,
          output,
          TokenChecks.componentTotal(fresh, cacheRead, cacheWrite, output));
    }
  }

  /**
   * 表示 PaginationDto 数据。
   *
   * @param page 当前页码。
   * @param pageSize 每页数量。
   * @param totalItems 该字段在 API 响应中的业务值。
   * @param totalPages 总页数。
   * @param hasPrevious 是否存在上一页。
   * @param hasNext 是否存在下一页。
   */
  public record PaginationDto(
      int page,
      int pageSize,
      long totalItems,
      int totalPages,
      boolean hasPrevious,
      boolean hasNext) {

    /** 校验字段和业务不变量。 */
    public PaginationDto {
      ParamChecks.atLeast(page, 1, "page");
      ParamChecks.atLeast(pageSize, 1, "pageSize");
      ParamChecks.nonNegative(totalItems, "totalItems");
      ParamChecks.nonNegative(totalPages, "totalPages");
    }

    /** 创建对应对象。 */
    public static PaginationDto of(int page, int pageSize, long totalItems) {
      int totalPages = totalItems == 0 ? 0 : (int) Math.ceil(totalItems / (double) pageSize);
      return new PaginationDto(
          page, pageSize, totalItems, totalPages, page > 1, totalPages > 0 && page < totalPages);
    }
  }

  /**
   * 表示 ApiLink 数据。
   *
   * @param rel 链接关系。
   * @param href 资源链接。
   * @param method HTTP 方法。
   */
  public record ApiLink(String rel, String href, String method) {

    /** 校验字段和业务不变量。 */
    public ApiLink {
      ParamChecks.nonBlank(rel, "rel");
      ParamChecks.nonBlank(href, "href");
      method = method == null || method.isBlank() ? "GET" : method;
    }

    /** 创建对应对象。 */
    public static ApiLink get(String rel, String href) {
      return new ApiLink(rel, href, "GET");
    }
  }

  /**
   * 表示 PageStateDto 数据。
   *
   * @param kind 该字段在 API 响应中的业务值。
   * @param reason 不可用原因。
   * @param title 会话标题。
   * @param message 消息文本。
   * @param actions 可用操作列表。
   */
  public record PageStateDto(
      String kind, String reason, String title, String message, List<ApiLink> actions) {

    /** 校验字段和业务不变量。 */
    public PageStateDto {
      ParamChecks.nonBlank(kind, "kind");
      reason = reason == null ? "" : reason;
      title = title == null ? "" : title;
      message = message == null ? "" : message;
      actions = ImmutableCopies.listOrEmpty(actions);
    }

    /** 就绪状态。 */
    public static PageStateDto ready() {
      return new PageStateDto("ready", "", "", "", List.of());
    }

    /** 数据集为空的状态。 */
    public static PageStateDto empty(String title, String message) {
      return new PageStateDto("empty", "empty_dataset", title, message, List.of());
    }

    /** 无结果状态。 */
    public static PageStateDto noResults(String title, String message, List<ApiLink> actions) {
      return new PageStateDto("no_results", "filter_no_results", title, message, actions);
    }
  }

  /**
   * 表示 SelectOptionDto 数据。
   *
   * @param value 字段原始值。
   * @param label 用户可读标签。
   */
  public record SelectOptionDto(String value, String label) {

    /** 校验字段和业务不变量。 */
    public SelectOptionDto {
      Objects.requireNonNull(value, "value must not be null");
      Objects.requireNonNull(label, "label must not be null");
    }
  }

  /**
   * 表示 ActiveFilterDto 数据。
   *
   * @param key 过滤条件字段名。
   * @param label 用户可读标签。
   * @param value 当前过滤值。
   * @param removeUrl 移除此过滤条件后的页面 URL。
   */
  public record ActiveFilterDto(String key, String label, String value, String removeUrl) {

    /** 校验字段和业务不变量。 */
    public ActiveFilterDto {
      key = ApiResponses.required(key, "key");
      label = ApiResponses.required(label, "label");
      value = ApiResponses.empty(value);
      removeUrl = ApiResponses.required(removeUrl, "removeUrl");
    }
  }

  /**
   * 表示 ActiveFiltersResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param chips 当前过滤条件 chip 列表。
   * @param clearAllUrl 清空全部过滤条件后的页面 URL。
   * @param state 页面或 API 状态描述。
   */
  public record ActiveFiltersResponse(
      String schemaVersion, List<ActiveFilterDto> chips, String clearAllUrl, PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ActiveFiltersResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(chips, "chips must not be null");
      clearAllUrl = ApiResponses.required(clearAllUrl, "clearAllUrl");
      Objects.requireNonNull(state, "state must not be null");
      chips = List.copyOf(chips);
    }
  }

  /**
   * 表示 PageStateModel 数据。
   *
   * @param kind 该字段在 API 响应中的业务值。
   * @param statusCode 该字段在 API 响应中的业务值。
   * @param title 会话标题。
   * @param message 消息文本。
   * @param role 该字段在 API 响应中的业务值。
   * @param ariaLive 该字段在 API 响应中的业务值。
   * @param actions 可用操作列表。
   * @param errorDetails 该字段在 API 响应中的业务值。
   */
  public record PageStateModel(
      String kind,
      int statusCode,
      String title,
      String message,
      String role,
      String ariaLive,
      List<ApiLink> actions,
      SafeErrorDetails errorDetails) {

    /** 校验字段和业务不变量。 */
    public PageStateModel {
      ParamChecks.nonBlank(kind, "kind");
      Objects.requireNonNull(title, "title must not be null");
      Objects.requireNonNull(message, "message must not be null");
      role = role == null || role.isBlank() ? "region" : role;
      ariaLive = ariaLive == null || ariaLive.isBlank() ? "polite" : ariaLive;
      actions = ImmutableCopies.listOrEmpty(actions);
      ParamChecks.inRange(statusCode, 100, 599, "statusCode");
    }

    /** 构建对应 DTO 数据。 */
    public static PageStateModel notFound(String message) {
      return new PageStateModel(
          "not_found",
          404,
          "Page Not Found",
          message,
          "region",
          "polite",
          List.of(
              ApiLink.get("dashboard", "/dashboard"),
              ApiLink.get("sessions", "/sessions"),
              ApiLink.get("projects", "/projects")),
          null);
    }

    /** 构建对应 DTO 数据。 */
    public static PageStateModel error(String message, SafeErrorDetails details) {
      return new PageStateModel(
          "error",
          500,
          "Something Went Wrong",
          message,
          "alert",
          "assertive",
          List.of(ApiLink.get("dashboard", "/dashboard"), ApiLink.get("reload", "#")),
          details);
    }
  }

  /**
   * 表示 SafeErrorDetails 数据。
   *
   * @param errorType 该字段在 API 响应中的业务值。
   * @param requestPath 该字段在 API 响应中的业务值。
   * @param requestId 标识符。
   * @param timestamp 该字段在 API 响应中的业务值。
   * @param messageSummary 该字段在 API 响应中的业务值。
   */
  public record SafeErrorDetails(
      String errorType,
      String requestPath,
      String requestId,
      String timestamp,
      String messageSummary) {

    private static final Pattern SECRET_PATTERN =
        Pattern.compile("(?i)(token|secret|password|apikey|api_key|authorization)\\s*[:=]\\s*\\S+");
    private static final Pattern HOME_PATH_PATTERN = Pattern.compile("(/Users/|/home/)[^\\s:]+");

    /** 校验字段和业务不变量。 */
    public SafeErrorDetails {
      errorType = safe(errorType);
      requestPath = sanitizePath(requestPath);
      requestId = safe(requestId);
      timestamp = safe(timestamp);
      messageSummary = sanitizeMessage(messageSummary);
    }

    private static String sanitizeMessage(String value) {
      String safe = safe(value);
      safe = SECRET_PATTERN.matcher(safe).replaceAll("$1=<redacted>");
      safe = HOME_PATH_PATTERN.matcher(safe).replaceAll("<path-redacted>");
      if (safe.length() > 240) {
        return safe.substring(0, 240) + "…";
      }
      return safe;
    }

    private static String sanitizePath(String value) {
      String safe = safe(value);
      if (safe.startsWith("/api/")
          || safe.startsWith("/sessions")
          || safe.startsWith("/projects")) {
        return safe;
      }
      return HOME_PATH_PATTERN.matcher(safe).find()
          ? "<path-redacted>"
          : (safe.startsWith("/") ? safe : "");
    }

    private static String safe(String value) {
      return value == null ? "" : value.replace('\n', ' ').replace('\r', ' ').trim();
    }
  }

  /**
   * 表示 EmptyStateDto 数据。
   *
   * @param kind 该字段在 API 响应中的业务值。
   * @param reason 不可用原因。
   * @param primaryAction 该字段在 API 响应中的业务值。
   * @param secondaryActions 该字段在 API 响应中的业务值。
   */
  public record EmptyStateDto(
      String kind, String reason, ApiLink primaryAction, List<ApiLink> secondaryActions) {

    /** 校验字段和业务不变量。 */
    public EmptyStateDto {
      Objects.requireNonNull(kind, "kind must not be null");
      reason = reason == null ? "" : reason;
      Objects.requireNonNull(primaryAction, "primaryAction must not be null");
      secondaryActions = ImmutableCopies.listOrEmpty(secondaryActions);
      if (!"empty".equals(kind) && !"no_results".equals(kind)) {
        throw new IllegalArgumentException("kind must be empty or no_results");
      }
    }
  }
}
