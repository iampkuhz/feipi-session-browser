package com.feipi.session.browser.quality.gates.core;

import java.nio.file.Path;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * 质量门执行上下文。
 *
 * <p>封装仓库根目录、输入路径、可选的文件列表来源和输出格式。
 */
public final class QualityGateContext {

  private final Path repoRoot;
  private final List<Path> inputPaths;
  private final Path filesFrom;
  private final Path reportFile;
  private final String format;
  private final Map<String, String> environment;

  private QualityGateContext(Builder builder) {
    this.repoRoot = Objects.requireNonNull(builder.repoRoot, "repoRoot");
    this.inputPaths = List.copyOf(builder.inputPaths);
    this.filesFrom = builder.filesFrom;
    this.reportFile = builder.reportFile;
    this.format = builder.format;
    this.environment = Collections.unmodifiableMap(new LinkedHashMap<>(builder.environment));
  }

  /**
   * 返回仓库根目录。
   *
   * @return 仓库根目录。
   */
  public Path repoRoot() {
    return repoRoot;
  }

  /**
   * 返回输入路径列表。
   *
   * @return 不可变输入路径列表。
   */
  public List<Path> inputPaths() {
    return inputPaths;
  }

  /**
   * 返回可选的文件列表来源路径。
   *
   * @return 文件列表路径；不存在时返回空。
   */
  public Optional<Path> filesFrom() {
    return Optional.ofNullable(filesFrom);
  }

  /**
   * 返回可选的报告输出路径。
   *
   * @return 报告文件路径；不存在时返回空。
   */
  public Optional<Path> reportFile() {
    return Optional.ofNullable(reportFile);
  }

  /**
   * 返回输出格式。
   *
   * @return {@code text} 或 {@code json}。
   */
  public String format() {
    return format;
  }

  /**
   * 返回环境变量映射。
   *
   * @return 不可变环境变量映射。
   */
  public Map<String, String> environment() {
    return environment;
  }

  /**
   * 创建新的 builder。
   *
   * @return builder 实例。
   */
  public static Builder builder() {
    return new Builder();
  }

  /** 质量门上下文构建器。 */
  public static final class Builder {

    private Path repoRoot;
    private List<Path> inputPaths = List.of();
    private Path filesFrom;
    private Path reportFile;
    private String format = "text";
    private final Map<String, String> environment = new LinkedHashMap<>();

    private Builder() {}

    /**
     * 设置仓库根目录。
     *
     * @param repoRoot 仓库根目录路径。
     * @return this。
     */
    public Builder repoRoot(Path repoRoot) {
      this.repoRoot = repoRoot;
      return this;
    }

    /**
     * 设置输入路径列表。
     *
     * @param inputPaths 输入路径列表。
     * @return this。
     */
    public Builder inputPaths(List<Path> inputPaths) {
      this.inputPaths = inputPaths;
      return this;
    }

    /**
     * 设置文件列表来源。
     *
     * @param filesFrom 文件列表路径。
     * @return this。
     */
    public Builder filesFrom(Path filesFrom) {
      this.filesFrom = filesFrom;
      return this;
    }

    /**
     * 设置报告输出路径。
     *
     * @param reportFile 报告文件路径。
     * @return this。
     */
    public Builder reportFile(Path reportFile) {
      this.reportFile = reportFile;
      return this;
    }

    /**
     * 设置输出格式。
     *
     * @param format {@code text} 或 {@code json}。
     * @return this。
     */
    public Builder format(String format) {
      this.format = format;
      return this;
    }

    /**
     * 设置环境变量。
     *
     * @param environment 环境变量映射。
     * @return this。
     */
    public Builder environment(Map<String, String> environment) {
      this.environment.clear();
      if (environment != null) {
        this.environment.putAll(environment);
      }
      return this;
    }

    /**
     * 构建上下文。
     *
     * @return 不可变上下文实例。
     */
    public QualityGateContext build() {
      return new QualityGateContext(this);
    }
  }
}
