package com.feipi.session.browser.reuse.analyzer.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Analyzer 的完整输入清单，由 Gradle 生成并传入。 包含模块信息、变更文件、base SHA 和策略 digest。 Analyzer 不自行调用 Gradle 或猜测
 * classpath。
 */
public final class InputManifest {

  private final int javaVersion;
  private final List<ModuleManifest> modules;
  private final List<String> changedFiles;
  private final String baseSha;
  private final String policyDigest;

  /** 创建输入清单实例。 */
  @JsonCreator
  public InputManifest(
      @JsonProperty("javaVersion") int javaVersion,
      @JsonProperty("modules") List<ModuleManifest> modules,
      @JsonProperty("changedFiles") List<String> changedFiles,
      @JsonProperty("baseSha") String baseSha,
      @JsonProperty("policyDigest") String policyDigest) {
    this.javaVersion = javaVersion;
    this.modules = modules != null ? List.copyOf(modules) : List.of();
    this.changedFiles = changedFiles != null ? List.copyOf(changedFiles) : List.of();
    this.baseSha = baseSha;
    this.policyDigest = policyDigest;
  }

  /** 获取 Java 版本。 */
  @JsonProperty("javaVersion")
  public int javaVersion() {
    return javaVersion;
  }

  /** 获取模块清单列表。 */
  @JsonProperty("modules")
  public List<ModuleManifest> modules() {
    return modules;
  }

  /** 获取变更文件列表。 */
  @JsonProperty("changedFiles")
  public List<String> changedFiles() {
    return changedFiles;
  }

  /** 获取基准提交的哈希标识。 */
  @JsonProperty("baseSha")
  public String baseSha() {
    return baseSha;
  }

  /** 获取策略 digest。 */
  @JsonProperty("policyDigest")
  public String policyDigest() {
    return policyDigest;
  }
}
