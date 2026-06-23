package com.feipi.session.browser.reuse.analyzer.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/** 分析结果，包含 findings 汇总和元数据。 */
public final class AnalysisResult {

  private final String status;
  private final int schemaVersion;
  private final List<Finding> findings;
  private final Map<String, Object> metadata;

  /** 创建分析结果实例。 */
  @JsonCreator
  public AnalysisResult(
      @JsonProperty("status") String status,
      @JsonProperty("schemaVersion") int schemaVersion,
      @JsonProperty("findings") List<Finding> findings,
      @JsonProperty("metadata") Map<String, Object> metadata) {
    this.status = status;
    this.schemaVersion = schemaVersion;
    this.findings = findings != null ? List.copyOf(findings) : List.of();
    this.metadata = metadata != null ? Map.copyOf(metadata) : Map.of();
  }

  /** 构造空结果（无 finding）。 */
  public static AnalysisResult empty() {
    return new AnalysisResult("PASS", 1, List.of(), Map.of());
  }

  /** 构造 BOOTSTRAP_REQUIRED 结果。 */
  public static AnalysisResult bootstrapRequired(String reason) {
    return new AnalysisResult("BOOTSTRAP_REQUIRED", 1, List.of(), Map.of("reason", reason));
  }

  /** 获取分析状态。 */
  @JsonProperty("status")
  public String status() {
    return status;
  }

  /** 获取 schema 版本。 */
  @JsonProperty("schemaVersion")
  public int schemaVersion() {
    return schemaVersion;
  }

  /** 获取 findings 列表。 */
  @JsonProperty("findings")
  public List<Finding> findings() {
    return findings;
  }

  /** 获取元数据。 */
  @JsonProperty("metadata")
  public Map<String, Object> metadata() {
    return metadata;
  }
}
