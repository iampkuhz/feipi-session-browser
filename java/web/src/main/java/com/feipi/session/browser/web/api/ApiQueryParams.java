package com.feipi.session.browser.web.api;

import io.javalin.http.Context;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

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

  /** 使用 UTF-8 对路径片段做 URL 编码，并将空格编码为 %20。 */
  static String url(String value) {
    return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8)
        .replace("+", "%20");
  }
}
