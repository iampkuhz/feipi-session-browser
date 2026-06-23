package com.feipi.session.browser.reuse.analyzer.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/** 单条代码复用 finding，表示一组重复或相似的代码。 包含指纹、occurrences、ownership、peer group 和建议决策。 */
public final class Finding {

  private final String id;
  private final Severity severity;
  private final String kind;
  private final String fingerprint;
  private final List<Map<String, Object>> occurrences;
  private final boolean touchesChangedCode;
  private final List<String> suggestedDecisions;
  private final Map<String, Object> ownership;
  private final String peerGroup;

  /** 创建单条 finding 实例。 */
  @JsonCreator
  public Finding(
      @JsonProperty("id") String id,
      @JsonProperty("severity") Severity severity,
      @JsonProperty("kind") String kind,
      @JsonProperty("fingerprint") String fingerprint,
      @JsonProperty("occurrences") List<Map<String, Object>> occurrences,
      @JsonProperty("touchesChangedCode") boolean touchesChangedCode,
      @JsonProperty("suggestedDecisions") List<String> suggestedDecisions,
      @JsonProperty("ownership") Map<String, Object> ownership,
      @JsonProperty("peerGroup") String peerGroup) {
    this.id = id;
    this.severity = severity;
    this.kind = kind;
    this.fingerprint = fingerprint;
    this.occurrences = occurrences != null ? List.copyOf(occurrences) : List.of();
    this.touchesChangedCode = touchesChangedCode;
    this.suggestedDecisions =
        suggestedDecisions != null ? List.copyOf(suggestedDecisions) : List.of();
    this.ownership = ownership != null ? Map.copyOf(ownership) : Map.of();
    this.peerGroup = peerGroup;
  }

  /** 获取 finding 标识。 */
  @JsonProperty("id")
  public String id() {
    return id;
  }

  /** 获取严重级别。 */
  @JsonProperty("severity")
  public Severity severity() {
    return severity;
  }

  /** 获取 finding 类型。 */
  @JsonProperty("kind")
  public String kind() {
    return kind;
  }

  /** 获取代码片段的指纹标识。 */
  @JsonProperty("fingerprint")
  public String fingerprint() {
    return fingerprint;
  }

  /** 获取 occurrence 列表。 */
  @JsonProperty("occurrences")
  public List<Map<String, Object>> occurrences() {
    return occurrences;
  }

  /** 是否涉及变更代码。 */
  @JsonProperty("touchesChangedCode")
  public boolean touchesChangedCode() {
    return touchesChangedCode;
  }

  /** 获取建议决策列表。 */
  @JsonProperty("suggestedDecisions")
  public List<String> suggestedDecisions() {
    return suggestedDecisions;
  }

  /** 获取 ownership 分布。 */
  @JsonProperty("ownership")
  public Map<String, Object> ownership() {
    return ownership;
  }

  /** 获取 peer group 标识。 */
  @JsonProperty("peerGroup")
  public String peerGroup() {
    return peerGroup;
  }
}
