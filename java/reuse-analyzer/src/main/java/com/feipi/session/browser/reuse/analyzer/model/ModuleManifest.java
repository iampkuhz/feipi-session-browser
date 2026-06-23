package com.feipi.session.browser.reuse.analyzer.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 单个模块的清单信息，由 Gradle 生成。 包含 production source roots、compile classpath 和编译输出。 */
public final class ModuleManifest {

  private final String id;
  private final List<String> productionSourceRoots;
  private final List<String> compileClasspath;
  private final List<String> compiledOutputs;

  /** 创建模块清单实例。 */
  @JsonCreator
  public ModuleManifest(
      @JsonProperty("id") String id,
      @JsonProperty("productionSourceRoots") List<String> productionSourceRoots,
      @JsonProperty("compileClasspath") List<String> compileClasspath,
      @JsonProperty("compiledOutputs") List<String> compiledOutputs) {
    this.id = id;
    this.productionSourceRoots =
        productionSourceRoots != null ? List.copyOf(productionSourceRoots) : List.of();
    this.compileClasspath = compileClasspath != null ? List.copyOf(compileClasspath) : List.of();
    this.compiledOutputs = compiledOutputs != null ? List.copyOf(compiledOutputs) : List.of();
  }

  /** 获取模块标识。 */
  @JsonProperty("id")
  public String id() {
    return id;
  }

  /** 获取 production source 目录列表。 */
  @JsonProperty("productionSourceRoots")
  public List<String> productionSourceRoots() {
    return productionSourceRoots;
  }

  /** 获取编译 classpath 列表。 */
  @JsonProperty("compileClasspath")
  public List<String> compileClasspath() {
    return compileClasspath;
  }

  /** 获取编译输出路径列表。 */
  @JsonProperty("compiledOutputs")
  public List<String> compiledOutputs() {
    return compiledOutputs;
  }
}
