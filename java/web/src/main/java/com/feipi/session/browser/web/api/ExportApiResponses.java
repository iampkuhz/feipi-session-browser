package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.List;
import java.util.Objects;

/** export contract APIs 的类型化 JSON 响应。 */
public final class ExportApiResponses {

  private ExportApiResponses() {}

  /**
   * 表示 ExportManifestResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param agent agent 类型标识。
   * @param sessionId provider session 标识符。
   * @param sessionKey 规范化 session key。
   * @param visibility 导出可见性策略。
   * @param maxBytes 最大字节数。
   * @param estimatedSizeBytes 预计导出字节数。
   * @param maxSizeBytes 最大允许导出字节数。
   * @param embeddedDataCapable 是否可嵌入离线数据。
   * @param offlineInteractionSupported 是否支持离线交互。
   * @param hasArtifact 是否存在导出 artifact。
   * @param roundCount round 数量。
   * @param payloadCount payload 数量。
   * @param formats 该字段在 API 响应中的业务值。
   * @param state 页面或 API 状态描述。
   */
  public record ExportManifestResponse(
      String schemaVersion,
      String agent,
      String sessionId,
      String sessionKey,
      String visibility,
      long maxBytes,
      long estimatedSizeBytes,
      long maxSizeBytes,
      boolean embeddedDataCapable,
      boolean offlineInteractionSupported,
      boolean hasArtifact,
      long roundCount,
      long payloadCount,
      List<ExportFormatDto> formats,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ExportManifestResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      agent = ApiResponses.required(agent, "agent");
      sessionId = ApiResponses.required(sessionId, "sessionId");
      sessionKey = ApiResponses.required(sessionKey, "sessionKey");
      visibility = ApiResponses.required(visibility, "visibility");
      Objects.requireNonNull(formats, "formats must not be null");
      Objects.requireNonNull(state, "state must not be null");
      formats = List.copyOf(formats);
      if (maxBytes < 1
          || estimatedSizeBytes < 0
          || maxSizeBytes < 1
          || roundCount < 0
          || payloadCount < 0) {
        throw new IllegalArgumentException("export manifest counts out of range");
      }
    }
  }

  /**
   * 表示 ExportFormatDto 数据。
   *
   * @param format 导出格式。
   * @param href 资源链接。
   * @param method HTTP 方法。
   * @param contentType 响应 content type。
   * @param offlineCapable 是否支持离线使用。
   */
  public record ExportFormatDto(
      String format, String href, String method, String contentType, boolean offlineCapable) {

    /** 校验字段和业务不变量。 */
    public ExportFormatDto {
      format = ApiResponses.required(format, "format");
      href = ApiResponses.required(href, "href");
      method = method == null || method.isBlank() ? "GET" : method;
      contentType = ApiResponses.required(contentType, "contentType");
    }
  }

  /**
   * 表示 ExportDataBundleResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param agent agent 类型标识。
   * @param sessionId provider session 标识符。
   * @param sessionKey 规范化 session key。
   * @param visibility 导出可见性策略。
   * @param tokens token 组成统计。
   * @param roundCount round 数量。
   * @param payloadCount payload 数量。
   * @param anomalyCount 异常数量。
   * @param rounds round 列表。
   * @param payloads payload 列表。
   * @param state 页面或 API 状态描述。
   */
  public record ExportDataBundleResponse(
      String schemaVersion,
      String agent,
      String sessionId,
      String sessionKey,
      String visibility,
      TokenSegments tokens,
      long roundCount,
      long payloadCount,
      int anomalyCount,
      List<SessionDetailApiResponses.RoundIndexDto> rounds,
      List<SessionDetailApiResponses.PayloadIndexDto> payloads,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public ExportDataBundleResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      agent = ApiResponses.required(agent, "agent");
      sessionId = ApiResponses.required(sessionId, "sessionId");
      sessionKey = ApiResponses.required(sessionKey, "sessionKey");
      visibility = ApiResponses.required(visibility, "visibility");
      Objects.requireNonNull(tokens, "tokens must not be null");
      Objects.requireNonNull(rounds, "rounds must not be null");
      Objects.requireNonNull(payloads, "payloads must not be null");
      Objects.requireNonNull(state, "state must not be null");
      rounds = List.copyOf(rounds);
      payloads = List.copyOf(payloads);
      if (roundCount < 0 || payloadCount < 0 || anomalyCount < 0) {
        throw new IllegalArgumentException("data bundle counts must be non-negative");
      }
    }
  }
}
