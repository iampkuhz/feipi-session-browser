package com.feipi.session.browser.web.api;

import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.web.model.PayloadVisibilityQuery;
import com.feipi.session.browser.web.page.QueryParams;
import io.javalin.http.Context;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/** API 查询解析和链接编码的共享辅助方法。 */
final class ApiQueryParams {

  private ApiQueryParams() {}

  /** 将 Javalin 多值查询 map 展平为每个 key 的首个值。 */
  static Map<String, String> flat(Context ctx) {
    Map<String, List<String>> raw = ctx.queryParamMap();
    Map<String, String> result = new HashMap<>();
    for (Map.Entry<String, List<String>> entry : raw.entrySet()) {
      List<String> values = entry.getValue();
      if (values != null && !values.isEmpty()) {
        result.put(entry.getKey(), values.get(0));
      }
    }
    return result;
  }

  /** 规范化排序方向为 asc 或 desc。 */
  static String normalizeDir(String value) {
    return "asc".equalsIgnoreCase(value) ? "asc" : "desc";
  }

  /** 将空查询值规范化为 all，其余值转为小写。 */
  static String normalizeAll(String value) {
    String normalized = Objects.toString(value, "").trim().toLowerCase(Locale.ROOT);
    return switch (normalized) {
      case "" -> "all";
      default -> normalized;
    };
  }

  /** 将路径中的 agent 别名规范化为索引中的 canonical agent。 */
  static String canonicalAgent(String agent) {
    return "claude-code".equals(agent) ? "claude_code" : agent;
  }

  /** 解析 payload visibility 查询参数。 */
  static PayloadVisibility payloadVisibility(Context ctx) {
    return PayloadVisibilityQuery.parse(ctx);
  }

  /** 构建会话列表 API 的 filter echo。 */
  static SessionsApiResponses.SessionsFilterEcho sessionsFilterEcho(Map<String, String> params) {
    return new SessionsApiResponses.SessionsFilterEcho(
        QueryParams.normalizeSessionAgent(params.getOrDefault("agent", "")),
        params.getOrDefault("model", ""),
        params.getOrDefault("project", ""),
        params.getOrDefault("status", ""),
        params.getOrDefault("q", ""),
        QueryParams.uiSortKey(params),
        normalizeDir(params.getOrDefault("dir", "desc")),
        QueryParams.parsePage(params),
        QueryParams.parsePageSize(params));
  }

  /** 使用 UTF-8 对路径片段做 URL 编码，并将空格编码为 %20。 */
  static String url(String value) {
    return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8)
        .replace("+", "%20");
  }
}
