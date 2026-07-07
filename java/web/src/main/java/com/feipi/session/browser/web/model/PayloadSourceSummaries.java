package com.feipi.session.browser.web.model;

import com.feipi.session.browser.query.api.PayloadSource;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Payload 来源展示摘要构造器。 */
public final class PayloadSourceSummaries {

  private PayloadSourceSummaries() {}

  /** 构建不含实际 payload 内容的展示摘要列表。 */
  public static List<Map<String, String>> build(List<PayloadSource> sources) {
    List<Map<String, String>> result = new ArrayList<>(sources.size());
    for (PayloadSource source : sources) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("payload_id", source.payloadId());
      entry.put("kind", source.kind().name().toLowerCase());
      entry.put("call_id", source.callId());
      entry.put("title", source.title());
      entry.put("truncated", source.truncated() ? "true" : "false");
      entry.put("status", source.truncated() ? "truncated" : "available");
      result.add(entry);
    }
    return result;
  }
}
